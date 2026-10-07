#!/usr/bin/env python3
"""Autonomous Intelligence Closure master status.

Machine-readable progress against the project-level A-E roadmap. This report is
descriptive and cannot alter research evidence, Promotion, or production rules.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"autonomous_intelligence_status.json"

def load(rel,default):
    try:return json.loads((ROOT/rel).read_text(encoding="utf-8"))
    except Exception:return default

def text(rel):
    try:return (ROOT/rel).read_text(encoding="utf-8")
    except Exception:return ""

def build():
    src=load("docs/data/source_intelligence.json",{})
    reading=load("docs/research/source_reading_memory.json",{})
    cand=load("docs/research/candidate_rule_status.json",{})
    replay=load("docs/research/candidate_rule_replay.json",{})
    forward=load("docs/research/candidate_forward_status.json",{})
    candidate_score=load("docs/research/candidate_eventscore_status.json",{})
    evidence=load("docs/research/evidence_status.json",{})
    system=load("docs/research/system_status.json",{})
    signal=load("docs/research/signal_governance.json",{})
    html=text("docs/index.html")
    product=text("docs/assets/product-intelligence.js")
    qa=text("scripts/autonomous_site_qa.mjs")

    source_count=int((src.get("counts") or {}).get("records") or len(src.get("records") or []))
    read_count=int((reading.get("counts") or {}).get("source_records") or len(reading.get("records") or []))
    ccounts=cand.get("counts") or {}
    rsum=replay.get("summary") or {}
    ev_forward=((evidence.get("evidence_layers") or {}).get("forward_evidence_candidates") or {})
    fcounts=forward.get("counts") or {}
    scounts=candidate_score.get("counts") or {}
    bridge=(candidate_score.get("promotion_gate_bridge") or {})
    promo=evidence.get("promotion") or {}
    outlet=(
        "唯一行动出口" in html
        and "single-action-outlet.js" in html
        and "single_action_outlet" in qa
        and "slice(0,5)" not in product
    )

    milestones={
      "A_source_reliability":{
        "state":"active_quality_hardening",
        "pass":source_count>0 and read_count>0,
        "metrics":{"source_records":source_count,"source_reading_records":read_count},
        "remaining":["primary_subject_attribution","continuous_source_coverage_audit"],
      },
      "B_autonomous_learning_core":{
        "state":"active" if int(ccounts.get("candidates") or 0)>=0 else "blocked",
        "pass":bool(cand.get("version")) and ccounts.get("production_eligible",0)==0,
        "metrics":ccounts,
        "remaining":["increase generic candidate coverage","resolve only source-defined indicator parameters"],
      },
      "C_validation_evidence":{
        "state":"engineering_active_evidence_maturing",
        "pass":bool(replay.get("version")) and replay.get("forward_evidence_mixed") is False and replay.get("production_effect")=="none",
        "metrics":{
            "replayed_candidates":rsum.get("replayed",0),
            "historical_replay_events":rsum.get("raw_events",0),
            "legacy_rule_forward_candidates":ev_forward.get("count",0),
            "compiled_forward_eligible_candidates":fcounts.get("eligible_candidates",0),
            "compiled_forward_state_entries":fcounts.get("state_entries",0),
            "compiled_forward_outcomes_5":fcounts.get("outcomes_5",0),
            "compiled_forward_outcomes_20":fcounts.get("outcomes_20",0),
            "compiled_forward_outcomes_60":fcounts.get("outcomes_60",0),
            "candidate_eventscore_events":scounts.get("events",0),
            "candidate_eventscore_scoreable":scounts.get("scoreable",0),
            "candidate_promotion_bridge_state":bridge.get("state","not_initialized"),
            "promotion_families_passed":promo.get("families_passed",0),
        },
        "remaining":[
            "first_genuine_forward_candidate_state_entry",
            "natural_20d_60d_maturity",
            "promotion_bridge_requires_explicit_signal_direction_governance_under_frozen_family_semantics"
        ],
      },
      "D_decision_fusion_watchlist":{
        "state":"partial",
        "pass":False,
        "metrics":{"learned_production_effect":signal.get("learned_production_effect","none")},
        "remaining":["position_awareness","promoted_method_scan_adapter","multi-evidence_decision_fusion","explicit_action_explanation_contract"],
      },
      "E_single_action_outlet":{
        "state":"implemented_qa_gated" if outlet else "attention_required",
        "pass":outlet,
        "metrics":{"today_cockpit_sole_outlet":outlet},
        "remaining":[] if outlet else ["restore single outlet contract"],
      },
    }
    blockers=[]
    if system.get("overall") in {"attention","unknown"}:blockers.append("system_health")
    if not milestones["E_single_action_outlet"]["pass"]:blockers.append("single_action_outlet")
    active="B_autonomous_learning_core"
    if milestones["B_autonomous_learning_core"]["pass"]:active="C_validation_evidence"
    if milestones["C_validation_evidence"]["pass"] and int(fcounts.get("outcomes_20") or 0)>0 and int(promo.get("families_passed") or 0)>0:active="D_decision_fusion_watchlist"
    return {
      "version":"1.0",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "formal_app_version":"6.9.0",
      "north_star":"Collect -> Understand -> Structure -> Validate -> Promote -> Scan -> Decide -> Explain -> Learn Again",
      "active_milestone":active,
      "blockers":blockers,
      "milestones":milestones,
      "development_policy":{
        "bug_fix_behavior":"fix + regression test + QA + automatically return to active milestone",
        "isolated_features_allowed":False,
        "today_cockpit_is_sole_action_outlet":True,
        "automatic_trading":False,
      },
    }

def main():
    out=build();OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"active_milestone":out["active_milestone"],"blockers":out["blockers"],"states":{k:v["state"] for k,v in out["milestones"].items()}},ensure_ascii=False))

if __name__=="__main__":main()
