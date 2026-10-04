#!/usr/bin/env python3
"""V6.15.8b Rule Family scorecards with clustered inference and FDR."""
from __future__ import annotations
import hashlib,json,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"family_scorecards.json"
VERSION="6.15.8b"

sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import block_bootstrap_ci,block_signflip_pvalue,benjamini_hochberg

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def iso_week(day):
    try:
        import pandas as pd
        ts=pd.Timestamp(str(day)[:10])
        iso=ts.isocalendar()
        return f"{int(iso.year):04d}-W{int(iso.week):02d}"
    except Exception:
        return "unknown"

def mean(vals):
    vals=[float(x) for x in vals if x is not None]
    return sum(vals)/len(vals) if vals else None

def _unit_rows(rows,h):
    grouped=defaultdict(list)
    for e in rows:
        score=(e.get("scores") or {}).get(str(h))
        if not score or score.get("unconditional_lift") is None:
            continue
        key=(str(e.get("author") or "unknown"),str(e.get("symbol") or "unknown"),iso_week(e.get("baseline_date")))
        grouped[key].append(e)
    units=[]
    for (author,symbol,week),evs in sorted(grouped.items()):
        scores=[(x.get("scores") or {}).get(str(h)) or {} for x in evs]
        units.append({
            "author":author,"symbol":symbol,"week":week,
            "events":len(evs),
            "lift":mean([s.get("unconditional_lift") for s in scores]),
            "return":mean([s.get("direction_adjusted_return") for s in scores]),
            "mae":mean([s.get("direction_adjusted_mae") for s in scores]),
            "benchmark_mae":mean([s.get("unconditional_baseline_direction_adjusted_mae") for s in scores]),
            "excess_vs_qqq":mean([s.get("excess_vs_qqq") for s in scores]),
        })
    return units

def build(events,families,spec):
    current_hash=(spec.get("definitions") or {}).get("rule_family_definition_hash")
    rule_to_family={}
    family_keys={}
    for a in families.get("assignments") or []:
        if not a.get("active") or a.get("definition_hash")!=current_hash:continue
        rule_to_family[a.get("rule_id")]=a.get("family_id")
        family_keys[a.get("family_id")]=a.get("family_key") or {}
    buckets=defaultdict(list)
    for e in events.get("events") or []:
        fid=rule_to_family.get(e.get("rule_id"))
        if fid:buckets[fid].append(e)

    defs=spec.get("definitions") or {}
    mt=(defs.get("multiple_testing") or {})
    min_clusters=int(mt.get("minimum_time_clusters_for_testing") or 6)
    resamples=int(mt.get("bootstrap_resamples") or 2000)
    seed=int(mt.get("bootstrap_seed") or 6158)
    q=float(mt.get("fdr_q") or 0.05)
    cards=[];pvals={}

    for fid,rows in sorted(buckets.items()):
        scoreable=[x for x in rows if x.get("scoreable")]
        authors=sorted({str(x.get("author") or "unknown") for x in scoreable})
        horizons={}
        for h in (5,20,60):
            matured=[x for x in scoreable if (x.get("scores") or {}).get(str(h))]
            units=_unit_rows(scoreable,h)
            weeks=defaultdict(list)
            for u in units:
                if u.get("lift") is not None:
                    weeks[u["week"]].append(u["lift"])
            block_values=[vals for _,vals in sorted(weeks.items())]
            block_means=[mean(vals) for vals in block_values]
            testable=len(block_values)>=min_clusters
            derived_seed=seed+int(hashlib.sha256(f"{fid}|{h}".encode()).hexdigest()[:8],16)%100000
            ci=block_bootstrap_ci(block_values,resamples,derived_seed) if testable else {
                "blocks":len(block_values),"n":len(units),"mean":mean([u.get("lift") for u in units]),"lower":None,"upper":None
            }
            p=block_signflip_pvalue(block_means,resamples,derived_seed) if testable else None
            key=f"{fid}|{h}"
            if p is not None:pvals[key]=p
            horizons[str(h)]={
                "raw_mature_events":len(matured),
                "effective_n":len(units),
                "independent_time_clusters":len(block_values),
                "independent_authors":len({u["author"] for u in units}),
                "direction_adjusted_return_mean":mean([u.get("return") for u in units]),
                "unconditional_lift_mean":mean([u.get("lift") for u in units]),
                "lift_ci95":ci,
                "excess_vs_qqq_mean":mean([u.get("excess_vs_qqq") for u in units]),
                "direction_adjusted_mae_mean":mean([u.get("mae") for u in units]),
                "benchmark_direction_adjusted_mae_mean":mean([u.get("benchmark_mae") for u in units]),
                "test_status":"testable" if testable else "not_testable",
                "p_value":p,
                "fdr":None,
            }
        cards.append({
            "family_id":fid,
            "family_key":family_keys.get(fid) or {},
            "member_rule_ids":sorted({x.get("rule_id") for x in rows if x.get("rule_id")}),
            "analysis_count":len(rows),
            "evidence_count":len({x.get("event_id") for x in scoreable}),
            "independent_authors":len(authors),
            "horizons":horizons,
        })

    fdr=benjamini_hochberg(pvals,q)
    for c in cards:
        for h in ("5","20","60"):
            key=f"{c['family_id']}|{h}"
            if key in fdr:c["horizons"][h]["fdr"]=fdr[key]
        h60=c["horizons"]["60"]
        c["status"]="statistically_reviewable" if (
            h60["effective_n"]>=int((spec.get("thresholds") or {}).get("mature_60_effective_samples_min") or 20)
            and c["independent_authors"]>=int((spec.get("thresholds") or {}).get("independent_authors_min") or 3)
            and h60["independent_time_clusters"]>=int((spec.get("thresholds") or {}).get("independent_time_clusters_min") or 6)
            and h60["test_status"]=="testable"
        ) else "sample_insufficient_research_only"

    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "definition_hash":current_hash,
        "multiple_testing":{"hypotheses_tested":len(pvals),"fdr_q":q,"method":"Benjamini-Hochberg"},
        "counts":{"families":len(cards),"reviewable":sum(1 for c in cards if c["status"]=="statistically_reviewable")},
        "cards":cards,
        "guardrails":[
            "Family membership is frozen before reading outcomes.",
            "Repeated events from the same author/symbol/week collapse into one effective unit.",
            "Bootstrap resamples complete ISO-week blocks.",
            "FDR is applied across all testable family x horizon hypotheses in one run.",
            "Below the minimum cluster count, inference is marked not_testable."
        ],
    }

def main():
    out=build(load(EVENTS,{}),load(FAMILIES,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
