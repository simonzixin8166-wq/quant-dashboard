#!/usr/bin/env python3
"""V6.15.7 Evidence Promotion Gate. Defaults closed."""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCORE=ROOT/"research"/"reports"/"rule_scorecards.json"
CONTRA=ROOT/"research"/"history"/"contradictions.json"
REGISTRY=ROOT/"research"/"registry"/"rules.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"promotion_gate.json"
VERSION="6.15.7"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(scorecards,contradictions,registry,events,spec):
    th=spec.get("thresholds") or {}
    meta={x.get("rule_id"):x for x in registry.get("rules") or []}
    unresolved=defaultdict(list)
    for c in contradictions.get("records") or []:
        if c.get("status")!="unresolved":continue
        p=c.get("payload") or {}
        ids=[]
        if p.get("rule_id"):ids.append(p["rule_id"])
        ids+=p.get("rule_ids") or []
        for rid in ids:unresolved[rid].append(c.get("contradiction_id"))
    event_by_rule=defaultdict(list)
    for e in events.get("events") or []:event_by_rule[e.get("rule_id")].append(e)
    rows=[]
    for c in scorecards.get("cards") or []:
        rid=c.get("rule_id");rmeta=meta.get(rid,{})
        h60=(c.get("horizons") or {}).get("60") or {}
        ci=h60.get("lift_ci95") or {}
        mae=h60.get("direction_adjusted_mae_mean")
        bmae=h60.get("benchmark_direction_adjusted_mae_mean")
        option_rule="Sell Put" in (rmeta.get("method_candidates") or []) or "LEAPS" in (rmeta.get("method_candidates") or [])
        option_real=not option_rule or any(e.get("scoreable") and e.get("direction")!="option_structure" for e in event_by_rule.get(rid,[]))
        data_ok=all((e.get("data_quality") or {}).get("status")=="ok" for e in event_by_rule.get(rid,[]) if e.get("triggered")) if event_by_rule.get(rid) else False
        conditions={
            "independent_authors":c.get("independent_authors",0)>=int(th.get("independent_authors_min",3)),
            "independent_time_clusters":c.get("independent_time_clusters",0)>=int(th.get("independent_time_clusters_min",6)),
            "mature_60_effective_samples":h60.get("mature_n",0)>=int(th.get("mature_60_effective_samples_min",20)),
            "lift_ci95_lower_bound_gt_zero":ci.get("lower") is not None and ci.get("lower")>float(th.get("lift_ci95_lower_bound_gt",0)),
            "mae_not_worse_than_benchmark":mae is not None and bmae is not None and mae>=bmae,
            "provenance_complete":bool(rmeta.get("source_snapshot_hash") and rmeta.get("normalized_rule_hash") and rmeta.get("url")),
            "price_data_consistent":data_ok,
            "no_unresolved_contradiction":not unresolved.get(rid),
            "option_has_real_contract_outcome":option_real,
        }
        passed=all(conditions.values())
        rows.append({
            "rule_id":rid,"spec_version":spec.get("spec_version"),"review_date":datetime.now(timezone.utc).date().isoformat(),
            "passed":passed,"state":"evaluated_evidence" if passed else "gate_closed",
            "conditions":conditions,
            "missing":[k for k,v in conditions.items() if not v],
            "production_effect":"none",
        })
    return {"version":VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"spec_version":spec.get("spec_version"),
      "counts":{"rules":len(rows),"passed":sum(1 for x in rows if x["passed"]),"closed":sum(1 for x in rows if not x["passed"])},
      "results":rows,
      "guardrails":[
       "Promotion never changes production rules, Planner weights, positions, allocations or orders.",
       "Threshold changes require a new evaluation spec version and must not be tuned to pass named methods.",
       "A closed gate is a valid and expected result when evidence is insufficient."
      ]}

def main():
    out=build(load(SCORE,{}),load(CONTRA,{}),load(REGISTRY,{}),load(EVENTS,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
