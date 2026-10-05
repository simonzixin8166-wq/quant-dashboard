#!/usr/bin/env python3
"""V6.15.8b Rule Family Evidence Promotion Gate.

The gate consumes family-level statistics only. Rule instances remain immutable
provenance atoms and are never promoted independently.
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCORE=ROOT/"research"/"reports"/"family_scorecards.json"
CONTRA=ROOT/"research"/"history"/"contradictions.json"
REGISTRY=ROOT/"research"/"registry"/"rules.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"promotion_gate.json"
VERSION="6.15.8i"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(scorecards,contradictions,registry,families,events,spec):
    th=spec.get("thresholds") or {}
    current_hash=(spec.get("definitions") or {}).get("rule_family_definition_hash")
    rule_meta={x.get("rule_id"):x for x in registry.get("rules") or []}
    family_members=defaultdict(set)
    rule_to_family={}
    for a in families.get("assignments") or []:
        if not a.get("active") or a.get("definition_hash")!=current_hash:continue
        family_members[a.get("family_id")].add(a.get("rule_id"))
        rule_to_family[a.get("rule_id")]=a.get("family_id")

    unresolved_by_family=defaultdict(list)
    for c in contradictions.get("records") or []:
        if c.get("status")!="unresolved":continue
        payload=c.get("payload") or {}
        ids=[]
        if payload.get("rule_id"):ids.append(payload["rule_id"])
        ids+=payload.get("rule_ids") or []
        for rid in ids:
            fid=rule_to_family.get(rid)
            if fid:unresolved_by_family[fid].append(c.get("contradiction_id"))

    events_by_family=defaultdict(list)
    for e in events.get("events") or []:
        fid=rule_to_family.get(e.get("rule_id"))
        if fid:events_by_family[fid].append(e)

    activation=(spec.get("promotion_activation") or {}).get("state")
    rows=[]
    for c in scorecards.get("cards") or []:
        fid=c.get("family_id")
        h60=(c.get("horizons") or {}).get("60") or {}
        ci=h60.get("lift_ci95") or {}
        fdr=h60.get("fdr") or {}
        mae=h60.get("direction_adjusted_mae_mean")
        bmae=h60.get("benchmark_direction_adjusted_mae_mean")
        mae_ci=h60.get("mae_noninferiority_ci95") or {}
        max_symbol_share=h60.get("single_symbol_effective_unit_share_max")
        key=c.get("family_key") or {}
        members=sorted(family_members.get(fid) or c.get("member_rule_ids") or [])
        option_family=key.get("instrument_type")=="option_structure" or key.get("primary_method") in {"Sell Put","LEAPS"}
        option_real=not option_family or any(
            e.get("scoreable") and e.get("direction")!="option_structure"
            for e in events_by_family.get(fid,[])
        )
        triggered=[e for e in events_by_family.get(fid,[]) if e.get("triggered")]
        data_ok=bool(triggered) and all((e.get("data_quality") or {}).get("status")=="ok" for e in triggered)
        provenance_ok=bool(members) and all(
            (rule_meta.get(rid) or {}).get("source_snapshot_hash")
            and (rule_meta.get(rid) or {}).get("normalized_rule_hash")
            and (rule_meta.get(rid) or {}).get("url")
            for rid in members
        )
        conditions={
            "independent_authors":h60.get("independent_authors",0)>=int(th.get("independent_authors_min",3)),
            "independent_time_clusters":h60.get("independent_time_clusters",0)>=int(th.get("independent_time_clusters_min",6)),
            "mature_60_effective_samples":h60.get("effective_n",0)>=int(th.get("mature_60_effective_samples_min",20)),
            "lift_ci95_lower_bound_gt_zero":ci.get("lower") is not None and ci.get("lower")>float(th.get("lift_ci95_lower_bound_gt",0)),
            "fdr_supported_60":bool(fdr.get("reject")),
            "mae_not_worse_than_benchmark":(
                mae_ci.get("lower") is not None
                and mae_ci.get("lower")>=float(th.get("mae_noninferiority_ci95_lower_bound_gte",0.0))
            ),
            "single_symbol_concentration_within_cap":(
                max_symbol_share is not None
                and max_symbol_share<=float(th.get("max_single_symbol_effective_unit_share",0.40))
            ),
            "provenance_complete":provenance_ok,
            "price_data_consistent":data_ok,
            "no_unresolved_contradiction":not unresolved_by_family.get(fid),
            "option_has_real_contract_outcome":option_real,
        }
        statistical_pass=all(conditions.values())
        activated=activation=="active"
        passed=statistical_pass and activated
        rows.append({
            "family_id":fid,
            "member_rule_ids":members,
            "spec_version":spec.get("spec_version"),
            "review_date":datetime.now(timezone.utc).date().isoformat(),
            "statistical_criteria_passed":statistical_pass,
            "promotion_activation_state":activation,
            "passed":passed,
            "state":"evaluated_evidence" if passed else ("shadow_criteria_pass" if statistical_pass else "gate_closed"),
            "conditions":conditions,
            "missing":[k for k,v in conditions.items() if not v],
            "production_effect":"none",
        })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "evaluation_unit":"rule_family",
        "counts":{
            "families":len(rows),
            "statistical_criteria_passed":sum(1 for x in rows if x["statistical_criteria_passed"]),
            "passed":sum(1 for x in rows if x["passed"]),
            "closed":sum(1 for x in rows if not x["passed"]),
        },
        "results":rows,
        "guardrails":[
            "Promotion is evaluated at the frozen Rule Family level, never at individual Rule instances.",
            "Promotion remains shadow-only until V6.15.8c statistical controls pass and a new spec activates it.",
            "Promotion never changes production rules, Planner weights, positions, allocations or orders.",
            "MAE noninferiority is decided by the pre-registered paired cluster-bootstrap lower bound, not a point estimate.",
            "No single symbol may exceed the pre-registered effective-unit share cap for Promotion.",
            "A closed gate is a valid and expected result when evidence is insufficient."
        ],
    }

def main():
    out=build(load(SCORE,{}),load(CONTRA,{}),load(REGISTRY,{}),load(FAMILIES,{}),load(EVENTS,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
