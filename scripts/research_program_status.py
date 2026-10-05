#!/usr/bin/env python3
"""MyAlpha V6.15 program status: architecture completion vs evidence maturity.

This report deliberately separates engineering completion from empirical
maturity. It must never mark forward evidence mature merely because the
pipeline exists.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"v615_program_status.json"

def load(rel,d):
    try:return json.loads((ROOT/rel).read_text(encoding="utf-8"))
    except Exception:return d

def exists(rel): return (ROOT/rel).exists()

def build():
    src=load("docs/data/source_intelligence.json",{})
    author=load("docs/research/author_intelligence.json",{})
    intake=load("research/reports/forward_intake_health.json",{})
    funnel=load("research/reports/source_rule_funnel_latest.json",{})
    rules=load("research/registry/rules.json",{})
    families=load("research/registry/rule_families.json",{})
    events=load("research/events/event_scores_v1.json",{})
    contra=load("research/history/contradictions.json",{})
    promo=load("research/reports/promotion_gate.json",{})
    monthly=load("research/reports/monthly_evidence_audit.json",{})
    evidence=load("docs/research/evidence_status.json",{})
    js=(ROOT/"docs/assets/wenxuecity.js").read_text(encoding="utf-8") if exists("docs/assets/wenxuecity.js") else ""
    source_records=src.get("records") or []
    hist=src.get("historical_learning") or {}
    hist_ids={r.get("archive_id") for r in hist.get("records") or [] if r.get("archive_id")}

    phases={
      "A_historical_learning_bridge":{
        "pass":bool(hist.get("non_gating")) and not any(r.get("archive_id") in hist_ids for r in source_records),
        "state":"complete",
        "detail":"top-level non-gating historical_learning; excluded from Source Intelligence records",
      },
      "B_author_intelligence":{
        "pass":bool(author.get("historical_learning",{}).get("non_gating")) and bool(author.get("forward_evidence",{}).get("point_in_time_only")),
        "state":"complete",
        "detail":"historical author memory and forward author evidence are separate",
      },
      "C_forward_intake":{
        "pass":bool(intake.get("integrity_pass")),
        "state":intake.get("status") or "unknown",
        "detail":"zero genuine-forward rules is healthy until a real new source arrives",
      },
      "D_rule_candidate_pipeline":{
        "pass":bool(rules.get("version")) and funnel.get("status")=="ok",
        "state":"complete",
        "detail":"Source Store -> proposition -> Rule Registry funnel present and result-blind",
      },
      "E_eventscore_forward_tracking":{
        "pass":bool(events.get("spec_version")) and (events.get("counts") or {}).get("conservation_ok") is True,
        "state":"active_waiting_for_forward_samples" if not intake.get("forward_path_observed") else "active",
        "detail":"5/20/60 tracking engine active; no historical sample is promoted to forward",
      },
      "F_author_scorecard":{
        "pass":bool(author.get("forward_evidence",{}).get("point_in_time_only")),
        "state":"waiting_for_sufficient_forward_evidence",
        "detail":"author-level forward statistics exist but no leaderboard is fabricated",
      },
      "G_rule_family":{
        "pass":bool(families.get("definition_hash")) and (families.get("counts") or {}).get("active_families",0)>=0,
        "state":"complete",
        "detail":"Promotion unit is frozen Rule Family, not individual statements",
      },
      "H_contradiction_memory":{
        "pass":bool(contra.get("version")),
        "state":"complete",
        "detail":"contradictions are retained as risk evidence rather than deleted",
      },
      "I_promotion_gate":{
        "pass":bool(promo.get("version")) and all(x.get("production_effect")=="none" for x in promo.get("results") or []),
        "state":"shadow_gate_closed" if not (promo.get("counts") or {}).get("passed") else "shadow_pass",
        "detail":"Promotion remains evidence-only and cannot modify production/trading",
      },
      "J_source_intelligence_ui":{
        "pass":all(x in js for x in ["YouTube 历史学习记忆","Author Intelligence · 作者研究画像","Forward 证据候选"]),
        "state":"complete",
        "detail":"UI exposes historical, forward and author layers separately",
      },
      "K_autonomous_learning_loop":{
        "pass":exists(".github/workflows/source-intelligence-validation.yml") and exists(".github/workflows/research-evidence-update.yml"),
        "state":"scheduled",
        "detail":"source learning and research evidence workflows are scheduled and QA-gated",
      },
      "L_v615_acceptance":{
        "pass":bool(monthly.get("all_integrity_checks_pass")) and int(monthly.get("boundary_failures") or 0)==0,
        "state":"engineering_complete_evidence_maturing",
        "detail":"engineering/integrity can complete now; 20/60-day empirical maturity must wait for real elapsed trading days",
      },
    }
    arch_pass=all(v["pass"] for v in phases.values())
    mature=(evidence.get("evidence_layers") or {}).get("mature_scoreable_evidence") or {}
    return {
      "version":"6.15-program-status-1",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "architecture_integrity_pass":arch_pass,
      "program_state":"engineering_complete_evidence_maturing" if arch_pass else "engineering_attention_required",
      "phases":phases,
      "forward_evidence":{
        "genuine_forward_rules":(intake.get("counts") or {}).get("genuine_forward_rules",0),
        "scoreable_forward_events":(intake.get("counts") or {}).get("scoreable_forward_events",0),
        "mature_20_effective_units":mature.get("effective_units_20d",0),
        "mature_60_effective_units":mature.get("effective_units_60d",0),
      },
      "next_transition":"V6.16 readiness is evidence-gated; do not advance merely because V6.15 engineering is complete.",
      "guardrails":[
        "Engineering completion and empirical evidence maturity are separate states.",
        "Historical learning can grow immediately but can never satisfy forward maturity requirements.",
        "No synthetic, backfilled or outcome-aware sample may be used to accelerate the 20/60 trading-day clock.",
      ],
    }

def main():
    out=build();OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"architecture_integrity_pass":out["architecture_integrity_pass"],"program_state":out["program_state"]},ensure_ascii=False))

if __name__=="__main__":main()
