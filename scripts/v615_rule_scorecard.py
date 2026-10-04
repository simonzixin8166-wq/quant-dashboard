#!/usr/bin/env python3
"""V6.15.5 rule scorecards from versioned EventScore evidence."""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
ATTR=ROOT/"research"/"state"/"method_attribution.json"
REGISTRY=ROOT/"research"/"registry"/"rules.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"rule_scorecards.json"
VERSION="6.15.5"
sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import ci95

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def month_cluster(x):
    d=str(x or "")[:7]
    return d if len(d)==7 else "unknown"

def mean(vals):
    vals=[float(x) for x in vals if x is not None]
    return sum(vals)/len(vals) if vals else None

def build(events,attr,registry,spec):
    attr_by_event={x.get("event_id"):x for x in attr.get("events") or []}
    rule_meta={x.get("rule_id"):x for x in registry.get("rules") or []}
    buckets=defaultdict(list)
    for e in events.get("events") or []:
        if e.get("rule_id"):buckets[e["rule_id"]].append(e)
    threshold=int((spec.get("thresholds") or {}).get("mature_60_effective_samples_min") or 20)
    cards=[]
    for rid,rows in sorted(buckets.items()):
        meta=rule_meta.get(rid,{})
        scoreable=[x for x in rows if x.get("scoreable")]
        authors={str(x.get("author") or meta.get("author") or "unknown") for x in scoreable}
        clusters={(str(x.get("author") or meta.get("author") or "unknown"),month_cluster(x.get("baseline_date"))) for x in scoreable}
        horizons={}
        for h in ("5","20","60"):
            matured=[x for x in scoreable if (x.get("scores") or {}).get(h)]
            lifts=[x["scores"][h].get("unconditional_lift") for x in matured if x["scores"][h].get("unconditional_lift") is not None]
            adj=[x["scores"][h].get("direction_adjusted_return") for x in matured if x["scores"][h].get("direction_adjusted_return") is not None]
            excess=[x["scores"][h].get("excess_vs_qqq") for x in matured if x["scores"][h].get("excess_vs_qqq") is not None]
            maes=[x["scores"][h].get("direction_adjusted_mae") for x in matured if x["scores"][h].get("direction_adjusted_mae") is not None]
            bmaes=[x["scores"][h].get("unconditional_baseline_direction_adjusted_mae") for x in matured if x["scores"][h].get("unconditional_baseline_direction_adjusted_mae") is not None]
            hrow={
                "mature_n":len(matured),
                "direction_adjusted_return_mean":mean(adj),
                "unconditional_lift_mean":mean(lifts),
                "lift_ci95":ci95(lifts),
                "excess_vs_qqq_mean":mean(excess),
                "direction_adjusted_mae_mean":mean(maes),
                "benchmark_direction_adjusted_mae_mean":mean(bmaes),
            }
            if len(matured)>=threshold:
                hrow["hit_rate"]=mean([1.0 if (x["scores"][h].get("direction_adjusted_return") or 0)>0 else 0.0 for x in matured])
            horizons[h]=hrow
        analysis_count=len(rows)
        evidence_count=len({x.get("event_id") for x in scoreable})
        primary=sorted({(attr_by_event.get(x.get("event_id")) or {}).get("primary_method") for x in rows if (attr_by_event.get(x.get("event_id")) or {}).get("primary_method")})
        cards.append({
            "rule_id":rid,
            "author":meta.get("author"),
            "title":meta.get("title"),
            "primary_methods":primary,
            "analysis_count":analysis_count,
            "evidence_count":evidence_count,
            "independent_authors":len(authors),
            "independent_time_clusters":len(clusters),
            "effective_sample_count":len(clusters),
            "status":"sample_insufficient_research_only" if horizons["60"]["mature_n"]<threshold else "statistically_reviewable",
            "horizons":horizons,
        })
    return {
        "version":VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),"counts":{"rules":len(cards),"reviewable":sum(1 for c in cards if c["status"]=="statistically_reviewable")},
        "cards":cards,
        "guardrails":[
            "analysis_count never contributes to evidence scoring.",
            "Small samples show status only; hit_rate is omitted below the frozen minimum sample threshold.",
            "Option structures without real contract outcomes remain unscored upstream.",
        ]
    }

def main():
    out=build(load(EVENTS,{}),load(ATTR,{}),load(REGISTRY,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
