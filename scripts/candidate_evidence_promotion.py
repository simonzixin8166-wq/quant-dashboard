#!/usr/bin/env python3
"""Candidate Evidence Promotion Gate v1.0.

Promotes statistically validated Candidate method families into a non-action
evidence tier that may later be consumed by Decision Fusion.

This gate does NOT create BUY/SELL actions, does NOT mutate the frozen Rule
Registry, and has no Production authority.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCORE=ROOT/"research"/"reports"/"candidate_family_scorecards.json"
REGISTRY=ROOT/"research"/"registry"/"candidate_rules.json"
EVENTS=ROOT/"research"/"events"/"candidate_event_scores_v1.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"candidate_evidence_promotion.json"
PUBLIC=ROOT/"docs"/"research"/"candidate_evidence_promotion_status.json"
VERSION="1.0"

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def build(scorecards,registry,events,spec):
    th=spec.get("thresholds") or {}
    candidates_by_family=defaultdict(list)
    for c in registry.get("candidates") or []:
        fid=str(c.get("family_signature") or "")
        if fid:candidates_by_family[fid].append(c)
    events_by_family=defaultdict(list)
    for e in events.get("events") or []:
        fid=str(e.get("family_signature") or "")
        if fid:events_by_family[fid].append(e)

    rows=[]
    for card in scorecards.get("cards") or []:
        fid=str(card.get("candidate_family_signature") or "")
        h60=(card.get("horizons") or {}).get("60") or {}
        ci=h60.get("lift_ci95") or {}
        fdr=h60.get("fdr") or {}
        mae_ci=h60.get("mae_noninferiority_ci95") or {}
        max_symbol_share=h60.get("single_symbol_effective_unit_share_max")
        members=candidates_by_family.get(fid,[])
        family_events=events_by_family.get(fid,[])
        scoreable=[e for e in family_events if e.get("scoreable")]
        directions={str(e.get("direction") or "") for e in scoreable}
        direction_ok=bool(scoreable) and directions.issubset({"bullish","bearish"})
        governance_ok=bool(members) and all(
            (c.get("signal_direction_governance") or {}).get("state")=="direction_governed"
            for c in members if c.get("reproducibility_status")=="machine_ready_shadow"
        )
        provenance_ok=bool(members) and all(
            c.get("source_id")
            and c.get("proposition_id")
            and (c.get("source") or {}).get("url")
            for c in members
        )
        data_ok=bool(scoreable) and all(
            (e.get("data_quality") or {}).get("status")=="ok"
            and (e.get("price_provenance") or {}).get("same_source") is True
            for e in scoreable
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
            "candidate_direction_governed":governance_ok,
            "event_directions_supported":direction_ok,
            "provenance_complete":provenance_ok,
            "price_data_consistent":data_ok,
        }
        passed=all(conditions.values())
        rows.append({
            "candidate_family_signature":fid,
            "spec_version":spec.get("spec_version"),
            "review_date":datetime.now(timezone.utc).date().isoformat(),
            "passed":passed,
            "state":"decision_fusion_evidence_eligible" if passed else "evidence_gate_closed",
            "conditions":conditions,
            "missing":[k for k,v in conditions.items() if not v],
            "member_candidate_ids":sorted(str(c.get("candidate_id")) for c in members if c.get("candidate_id")),
            "direction_semantics":"research_outcome_direction_not_trade_action",
            "trade_action":None,
            "decision_fusion_eligible":passed,
            "production_eligible":False,
            "production_effect":"none",
        })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "promotion_unit":"candidate_method_family_evidence",
        "counts":{
            "families":len(rows),
            "passed":sum(1 for x in rows if x["passed"]),
            "closed":sum(1 for x in rows if not x["passed"]),
            "decision_fusion_eligible":sum(1 for x in rows if x["decision_fusion_eligible"]),
        },
        "results":rows,
        "promotion_effect":"evidence_tier_only",
        "production_effect":"none",
        "guardrails":[
            "The gate reuses frozen Spec 1.7 statistical thresholds without tuning to named methods.",
            "Candidate signal direction is outcome-scoring semantics only and is never mapped to BUY/SELL.",
            "Passing grants eligibility as one evidence input to future Decision Fusion only.",
            "Passing cannot modify protected rules, positions, sizing, allocations, or orders.",
            "Zero passed families is a valid state while genuine Forward evidence accumulates.",
        ],
    }

def public_status(out):
    return {
        "version":out.get("version"),
        "generated_at":out.get("generated_at"),
        "spec_version":out.get("spec_version"),
        "counts":out.get("counts"),
        "state":"evidence_gate_ready",
        "promotion_unit":out.get("promotion_unit"),
        "promotion_effect":out.get("promotion_effect"),
        "production_effect":"none",
    }

def main():
    out=build(load(SCORE,{}),load(REGISTRY,{}),load(EVENTS,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    PUBLIC.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PUBLIC.write_text(json.dumps(public_status(out),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
