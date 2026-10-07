#!/usr/bin/env python3
"""Candidate Parameter Definition Queue v1.0.

Tracks unresolved source-defined indicator parameters for Research/Shadow
candidates. It never supplies defaults and never infers missing formulas.

Purpose:
- make missing definitions explicit and auditable;
- preserve source/candidate provenance;
- distinguish engineering readiness from external evidence dependency;
- automatically clear an item only when the Candidate compiler no longer
  reports that unresolved input.

This module has no Production, Promotion, position, sizing, or order authority.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"registry"/"candidate_rules.json"
OUT=ROOT/"docs"/"research"/"candidate_parameter_queue.json"
VERSION="1.0"

PARAMETERIZED={
    "supertrend_bullish":{
        "needed":["atr_period","multiplier"],
        "definition_requirement":"Source must explicitly define Supertrend ATR period and multiplier."
    },
    "macd_hist_positive":{
        "needed":["fast_period","slow_period","signal_period"],
        "definition_requirement":"Source must explicitly define MACD fast/slow/signal periods."
    },
    "ppo_above_signal":{
        "needed":["fast_period","slow_period","signal_period"],
        "definition_requirement":"Source must explicitly define PPO periods and signal construction."
    },
    "ppo_hist_positive":{
        "needed":["fast_period","slow_period","signal_period"],
        "definition_requirement":"Source must explicitly define PPO periods and histogram construction."
    },
    "tcds_cross_zero":{
        "needed":["formula","input_series","parameters"],
        "definition_requirement":"Source must explicitly define the TCDS formula, inputs, and parameters."
    },
}

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def build(registry):
    rows=[]
    for c in registry.get("candidates") or []:
        unresolved={str(x.get("condition_id") or ""):x for x in (c.get("unresolved_inputs") or []) if isinstance(x,dict)}
        for cid,meta in PARAMETERIZED.items():
            if cid not in unresolved:continue
            src=c.get("source") or {}
            rows.append({
                "candidate_id":c.get("candidate_id"),
                "family_signature":c.get("family_signature"),
                "condition_id":cid,
                "method_family":c.get("method_family"),
                "state_role":c.get("state_role"),
                "symbols":(c.get("scope") or {}).get("symbols") or [],
                "author":src.get("author"),
                "title":src.get("title"),
                "published_at":src.get("published_at"),
                "url":src.get("url"),
                "needed_parameters":list(meta["needed"]),
                "compiler_reason":unresolved[cid].get("reason"),
                "definition_requirement":meta["definition_requirement"],
                "resolution_state":"awaiting_explicit_source_definition",
                "can_use_default_parameters":False,
                "production_eligible":False,
                "promotion_eligible":False,
            })

    by_condition=Counter(x["condition_id"] for x in rows)
    by_author=Counter(x.get("author") or "unknown" for x in rows)
    unique_sources={(x.get("url"),x.get("condition_id")) for x in rows}
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "state":"waiting_for_source_definitions" if rows else "all_parameterized_conditions_resolved",
        "counts":{
            "queue_items":len(rows),
            "unique_source_condition_pairs":len(unique_sources),
            "conditions_waiting":len(by_condition),
            "candidates_affected":len({x["candidate_id"] for x in rows}),
        },
        "by_condition":dict(sorted(by_condition.items())),
        "by_author":dict(sorted(by_author.items())),
        "items":rows,
        "resolution_policy":{
            "allowed":"Only explicit source-authored formula/period/multiplier definitions may resolve an item.",
            "forbidden":[
                "industry-default parameter substitution",
                "model-guessed parameter values",
                "retroactive relabeling of historical evidence as Forward",
                "silent Promotion or Production eligibility changes"
            ],
        },
        "production_effect":"none",
        "promotion_effect":"none",
        "guardrails":[
            "Queue items are evidence dependencies, not engineering failures.",
            "No default indicator parameters are permitted.",
            "A queue item disappears only when the compiler no longer reports the unresolved condition.",
            "Resolving an old historical Candidate does not make it Forward evidence.",
            "This queue cannot change protected rules, positions, sizing, Promotion, or orders.",
        ],
    }

def main():
    out=build(load(REGISTRY,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":out["state"],"counts":out["counts"],"by_condition":out["by_condition"]},ensure_ascii=False))

if __name__=="__main__":main()
