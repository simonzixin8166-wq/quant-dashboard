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
VERSION="6.15.8d"

sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import block_bootstrap_ci,block_signflip_pvalue,benjamini_hochberg

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def week_index(day):
    try:
        import pandas as pd
        ts=pd.Timestamp(str(day)[:10])
        # Monday-based absolute week index, stable across years.
        monday=ts-pd.Timedelta(days=int(ts.weekday()))
        return int(monday.toordinal()//7)
    except Exception:
        return None

def horizon_block_id(day,horizon_weeks):
    wi=week_index(day)
    if wi is None:return "unknown"
    return f"block-{wi//max(1,int(horizon_weeks))}"

def mean(vals):
    vals=[float(x) for x in vals if x is not None]
    return sum(vals)/len(vals) if vals else None

def _unit_rows(rows,h,horizon_weeks):
    """Collapse author duplicates into one symbol x non-overlapping horizon block unit."""
    grouped=defaultdict(list)
    for e in rows:
        score=(e.get("scores") or {}).get(str(h))
        if not score or score.get("unconditional_lift") is None:
            continue
        block=horizon_block_id(e.get("baseline_date"),horizon_weeks)
        key=(str(e.get("symbol") or "unknown"),block)
        grouped[key].append(e)
    units=[]
    for (symbol,block),evs in sorted(grouped.items()):
        scores=[(x.get("scores") or {}).get(str(h)) or {} for x in evs]
        authors=sorted({str(x.get("author") or "unknown") for x in evs})
        units.append({
            "symbol":symbol,"block":block,"authors":authors,
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
    for fid in sorted(set(rule_to_family.values())):
        buckets[fid]=[]
    for e in events.get("events") or []:
        fid=rule_to_family.get(e.get("rule_id"))
        if fid:buckets[fid].append(e)

    defs=spec.get("definitions") or {}
    mt=(defs.get("multiple_testing") or {})
    clustering=(defs.get("clustering") or {})
    block_weeks={str(k):int(v) for k,v in (clustering.get("horizon_block_weeks") or {"5":1,"20":4,"60":12}).items()}
    min_clusters=int(mt.get("minimum_time_clusters_for_testing") or 6)
    resamples=int(mt.get("bootstrap_resamples") or 2000)
    seed=int(mt.get("bootstrap_seed") or 6158)
    q=float(mt.get("fdr_q") or 0.05)
    horizons_declared=[int(x) for x in (defs.get("horizons_trading_days") or [5,20,60])]
    cards=[];pvals={}

    for fid,rows in sorted(buckets.items()):
        scoreable=[x for x in rows if x.get("scoreable")]
        authors=sorted({str(x.get("author") or "unknown") for x in scoreable})
        horizons={}
        for h in horizons_declared:
            matured=[x for x in scoreable if (x.get("scores") or {}).get(str(h))]
            units=_unit_rows(scoreable,h,block_weeks.get(str(h),1))
            blocks=defaultdict(list)
            for u in units:
                if u.get("lift") is not None:
                    blocks[u["block"]].append(u["lift"])
            block_values=[vals for _,vals in sorted(blocks.items())]
            block_means=[mean(vals) for vals in block_values]
            testable=len(block_values)>=min_clusters
            derived_seed=seed+int(hashlib.sha256(f"{fid}|{h}".encode()).hexdigest()[:8],16)%100000
            ci=block_bootstrap_ci(block_values,resamples,derived_seed) if testable else {
                "blocks":len(block_values),"n":len(units),"mean":mean([u.get("lift") for u in units]),"lower":None,"upper":None
            }
            p=block_signflip_pvalue(block_means,resamples,derived_seed) if testable else None
            key=f"{fid}|{h}"
            # Full frozen hypothesis family: untestable hypotheses enter FDR with p=1.
            pvals[key]=p if p is not None else float(mt.get("untestable_hypothesis_pvalue_for_fdr",1.0))
            horizons[str(h)]={
                "raw_mature_events":len(matured),
                "effective_n":len(units),
                "independent_time_clusters":len(block_values),
                "independent_authors":len({a for u in units for a in (u.get("authors") or [])}),
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

    expected_hypotheses=len(cards)*len(horizons_declared)
    if len(pvals)!=expected_hypotheses:
        raise AssertionError(f"FDR family incomplete: {len(pvals)} != {expected_hypotheses}")
    fdr=benjamini_hochberg(pvals,q)
    for c in cards:
        for h in [str(x) for x in horizons_declared]:
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
        "multiple_testing":{"hypotheses_declared":len(pvals),"hypotheses_testable":sum(1 for c in cards for h in c["horizons"].values() if h.get("test_status")=="testable"),"fdr_q":q,"method":"Benjamini-Hochberg","untestable_pvalue":float(mt.get("untestable_hypothesis_pvalue_for_fdr",1.0))},
        "counts":{"families":len(cards),"reviewable":sum(1 for c in cards if c["status"]=="statistically_reviewable")},
        "cards":cards,
        "guardrails":[
            "Family membership is frozen before reading outcomes.",
            "Effective sample size is symbol x non-overlapping horizon block; author count is reported separately.",
            "Bootstrap resamples complete non-overlapping horizon blocks; all symbols in a block stay together.",
            "FDR is applied to the full frozen active-family x declared-horizon hypothesis set; untestable hypotheses enter as p=1.",
            "Below the minimum cluster count, inference is marked not_testable."
        ],
    }

def main():
    out=build(load(EVENTS,{}),load(FAMILIES,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
