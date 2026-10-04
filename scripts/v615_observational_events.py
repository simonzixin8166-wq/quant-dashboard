#!/usr/bin/env python3
"""V6.15.8b descriptive observational events.

Author-reported actions without a registered testable rule are preserved for
research context only. They never enter method scoring, family scorecards,
promotion, planner weighting or production logic.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
VALIDATION=ROOT/"docs"/"research"/"source_outcome_validation.json"
OUT=ROOT/"research"/"events"/"observational_events.json"
VERSION="6.15.8b"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(events,validation):
    legacy={str(x.get("event_id")):x for x in validation.get("events") or []}
    rows=[]
    for e in events.get("events") or []:
        if e.get("primary_exclusion_reason")!="missing_rule_id":
            continue
        old=legacy.get(str(e.get("event_id"))) or {}
        op=old.get("operation") or {}
        attribution=op.get("attribution")
        if attribution=="third_party_example":
            continue
        rows.append({
            "observation_id":"obs_"+str(e.get("event_id")),
            "event_id":e.get("event_id"),
            "source_id":e.get("legacy_source_id"),
            "author":e.get("author"),
            "symbol":e.get("symbol"),
            "published_at":e.get("published_at"),
            "baseline_date":e.get("baseline_date"),
            "operation_attribution":attribution or "unconfirmed_author_context",
            "entry_type":e.get("entry_type"),
            "fill_status":e.get("fill_status"),
            "description_role":"descriptive_non_validating",
            "promotion_eligible":False,
            "method_score_eligible":False,
            "planner_weight_eligible":False,
            "inference_confidence":op.get("attribution_confidence") or "needs_review",
            "inference_source":"legacy_operation_attribution",
        })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "counts":{"observations":len(rows)},
        "events":rows,
        "guardrails":[
            "Observational events are descriptive, not validated evidence.",
            "They cannot enter lift, method scoring, Promotion Gate or Planner weighting.",
            "They preserve author/context provenance without promoting old operations into rules."
        ],
    }

def main():
    out=build(load(EVENTS,{}),load(VALIDATION,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
