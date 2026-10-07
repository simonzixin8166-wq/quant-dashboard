#!/usr/bin/env python3
"""Candidate EventScore adapter v1.0.

Transforms append-only compiled-candidate Forward observations into the same
core metric vocabulary used by Evaluation Spec 1.7 while keeping them outside
the existing Rule Promotion Gate until frozen Rule Family semantics explicitly
support signal-derived direction.

This adapter never creates rule_ids, never mutates Promotion, and never changes
Production.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from candidate_forward_observer import load_ledger
    from evaluation_spec import load_spec, direction_adjusted_return
    from v615_event_score import (
        baseline_timestamp_utc,
        build_histories,
        direction_adjusted_excursions,
        historical_unconditional_metrics,
    )
except ModuleNotFoundError:
    from scripts.candidate_forward_observer import load_ledger
    from scripts.evaluation_spec import load_spec, direction_adjusted_return
    from scripts.v615_event_score import (
        baseline_timestamp_utc,
        build_histories,
        direction_adjusted_excursions,
        historical_unconditional_metrics,
    )

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"research"/"history"/"candidate_forward_events.jsonl"
OUT=ROOT/"research"/"events"/"candidate_event_scores_v1.json"
PUBLIC=ROOT/"docs"/"research"/"candidate_eventscore_status.json"
VERSION="1.0"
ENGINE="candidate_event_score@1.0"
HORIZONS=(5,20,60)

def finite(v):
    try:
        x=float(v)
        return x if pd.notna(x) else None
    except Exception:return None

def point_in_time_status(entry,baseline,spec):
    if not baseline:return "awaiting_next_session_open"
    if entry.get("source_admission_class")!="genuine_forward":
        return "source_not_genuine_forward"
    first=entry.get("candidate_first_compiler_seen_at")
    fetched=entry.get("source_first_fetched_at")
    if not first or not fetched:return "timestamp_provenance_unknown"
    try:
        bt=baseline_timestamp_utc(baseline.get("baseline_date"),spec)
        ft=pd.Timestamp(first); st=pd.Timestamp(fetched)
        if ft.tzinfo is None or st.tzinfo is None or bt is None:return "timestamp_provenance_unknown"
        bt=pd.Timestamp(bt)
        if bt<=ft.tz_convert("UTC") or bt<=st.tz_convert("UTC"):
            return "historical_pre_formation"
        return "eligible"
    except Exception:return "timestamp_provenance_unknown"

def primary_exclusion(entry,baseline,hmeta,pit):
    if not entry.get("candidate_snapshot_hash"):return "missing_candidate_snapshot"
    if baseline is None:return "missing_next_session_open_baseline"
    if pit!="eligible":return pit
    status=(hmeta or {}).get("status")
    if status=="conflict":return "price_source_conflict"
    if status=="cache_only_unscored":return "cache_only_unscored"
    if status!="ok":return "missing_price_data"
    if (hmeta or {}).get("price_source")!="stooq_archive":return "noncanonical_price_source"
    return None

def adapt(rows,histories,spec):
    entries={x.get("event_id"):x for x in rows if x.get("record_type")=="state_entry" and x.get("event_id")}
    baselines={x.get("event_id"):x for x in rows if x.get("record_type")=="baseline" and x.get("event_id")}
    outcomes={}
    for x in rows:
        if x.get("record_type")=="outcome" and x.get("event_id") and x.get("horizon") is not None:
            outcomes[(x.get("event_id"),int(x.get("horizon")))]=x
    events=[]
    for eid,entry in sorted(entries.items()):
        symbol=str(entry.get("symbol") or "")
        baseline=baselines.get(eid)
        hctx=histories.get(symbol) or {}
        hmeta=hctx.get("meta") or {}
        df=hctx.get("df")
        pit=point_in_time_status(entry,baseline,spec)
        primary=primary_exclusion(entry,baseline,hmeta,pit)
        direction=entry.get("expected_direction")
        if direction not in {"bullish","bearish"} and primary is None:
            primary="unsupported_direction"
        scoreable=primary is None
        scores={}
        for h in HORIZONS:
            old=outcomes.get((eid,h))
            if not old:
                scores[str(h)]=None
                continue
            raw=finite(old.get("return"))
            raw_mae=finite(old.get("mae"));raw_mfe=finite(old.get("mfe"))
            adj=direction_adjusted_return(direction,raw)
            adj_mae,adj_mfe=direction_adjusted_excursions(direction,raw_mae,raw_mfe)
            hist=historical_unconditional_metrics(df,(baseline or {}).get("baseline_date"),h,direction)
            uncond=(hist or {}).get("direction_adjusted_return")
            scores[str(h)]={
                "horizon_end_date":old.get("maturity_date"),
                "raw_return":raw,
                "direction_adjusted_return":adj,
                "benchmark_return":old.get("benchmark_return"),
                "excess_vs_qqq":old.get("excess_vs_qqq"),
                "unconditional_baseline_direction_adjusted_return":uncond,
                "unconditional_baseline_direction_adjusted_mae":(hist or {}).get("direction_adjusted_mae"),
                "unconditional_baseline_n":(hist or {}).get("n"),
                "unconditional_lift":None if adj is None or uncond is None else adj-uncond,
                "mae":raw_mae,
                "mfe":raw_mfe,
                "direction_adjusted_mae":adj_mae,
                "direction_adjusted_mfe":adj_mfe,
            }
        events.append({
            "event_id":eid,
            "candidate_id":entry.get("candidate_id"),
            "family_signature":entry.get("family_signature"),
            "candidate_snapshot_hash":entry.get("candidate_snapshot_hash"),
            "spec_version":spec.get("spec_version"),
            "scoring_engine_version":ENGINE,
            "author":entry.get("author"),
            "source_id":entry.get("source_id"),
            "source_url":entry.get("source_url"),
            "symbol":symbol,
            "signal_date":entry.get("signal_date"),
            "baseline_date":(baseline or {}).get("baseline_date"),
            "baseline_timestamp_utc":(
                baseline_timestamp_utc((baseline or {}).get("baseline_date"),spec).isoformat()
                if baseline and baseline_timestamp_utc(baseline.get("baseline_date"),spec) is not None else None
            ),
            "entry_type":"next_session",
            "entry_semantics":"next_session_open_after_completed_daily_signal",
            "direction":direction,
            "triggered":True,
            "scoreable":scoreable,
            "primary_exclusion_reason":primary,
            "point_in_time_status":pit,
            "maturity":{str(h):outcomes.get((eid,h)) is not None for h in HORIZONS},
            "scores":scores,
            "data_quality":hmeta,
            "price_provenance":{
                "price_source":hmeta.get("price_source"),
                "adjustment_basis":hmeta.get("adjustment_basis"),
                "baseline_source":hmeta.get("price_source"),
                "horizon_source":hmeta.get("price_source"),
                "same_source":bool(hmeta.get("same_source_only")),
            },
            "promotion_gate_compatible":False,
            "promotion_gate_blocker":"frozen_rule_family_direction_requires_explicit_operation_action_semantics",
        })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "scoring_engine_version":ENGINE,
        "mode":"compiled_candidate_forward_eventscore_research_only",
        "counts":{
            "events":len(events),
            "scoreable":sum(1 for x in events if x.get("scoreable")),
            "mature_5":sum(1 for x in events if x["maturity"]["5"]),
            "mature_20":sum(1 for x in events if x["maturity"]["20"]),
            "mature_60":sum(1 for x in events if x["maturity"]["60"]),
            "promotion_gate_compatible":0,
        },
        "events":events,
        "production_effect":"none",
        "promotion_effect":"none",
        "guardrails":[
            "Metrics reuse Evaluation Spec 1.7 definitions: next-session open baseline, direction-adjusted return, prior-only unconditional lift, MAE/MFE and QQQ excess.",
            "STOOQ remains canonical; cache-only or conflicting histories are unscored.",
            "Candidate EventScore does not create or infer a Rule Registry action.",
            "Frozen Rule Family direction is action-derived; compiled signal direction cannot be silently mapped to buy/sell.",
            "Legacy Rule Promotion compatibility remains false; Candidate Evidence Promotion is handled by a separate evidence-only gate with no trade-action semantics.",
            "No Production mutation or automatic trading is possible from this adapter.",
        ],
    }

def public_status(out):
    return {
        "version":out.get("version"),
        "generated_at":out.get("generated_at"),
        "spec_version":out.get("spec_version"),
        "counts":out.get("counts"),
        "promotion_gate_bridge":{
            "state":"legacy_rule_promotion_bridge_frozen",
            "blocker":"Frozen Rule Family v1.3 remains action-derived and is intentionally not used for Candidate evidence promotion.",
            "required_resolution":"none for Candidate evidence tier; use candidate_evidence_promotion_status.json. Any future mapping to Production actions requires separate reviewed governance.",
            "candidate_evidence_promotion_path":"independent_ready",
        },
        "production_effect":"none",
        "promotion_effect":"none",
    }

def main():
    spec=load_spec()
    out=adapt(load_ledger(LEDGER),build_histories(),spec)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PUBLIC.parent.mkdir(parents=True,exist_ok=True)
    PUBLIC.write_text(json.dumps(public_status(out),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
