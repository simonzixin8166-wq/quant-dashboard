#!/usr/bin/env python3
"""Build the public, non-sensitive research-evidence status used by the Research Center UI.

This is a presentation adapter only. It never changes research evidence,
Promotion, Readiness, thresholds, or any production trading rule.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
COEX=ROOT/"research"/"audit"/"eventscore_spec_coexistence.json"
READINESS=ROOT/"research"/"reports"/"v616_readiness_gate.json"
FAMILY=ROOT/"research"/"reports"/"family_feasibility.json"
PROMOTION=ROOT/"research"/"reports"/"promotion_gate.json"
FORWARD_HEALTH=ROOT/"research"/"reports"/"forward_intake_health.json"
FUNNEL=ROOT/"research"/"reports"/"source_rule_funnel_latest.json"
OUT=ROOT/"docs"/"research"/"evidence_status.json"
VERSION="1.0"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def build(events, coexistence, readiness, family, promotion, forward_health, funnel=None):
    rows=events.get("events") or []
    forward=[e for e in rows if e.get("point_in_time_status")=="eligible"]
    scoreable=[e for e in forward if e.get("scoreable")]
    mature20=[e for e in scoreable if (e.get("scores") or {}).get("20")]
    mature60=[e for e in scoreable if (e.get("scores") or {}).get("60")]
    co_counts=coexistence.get("counts") or {}
    rd=readiness.get("observed") or {}
    fam_counts=family.get("counts") or {}
    promo_counts=promotion.get("counts") or {}
    funnel=funnel or {}
    funnel_down=funnel.get("downstream_counts") or {}
    funnel_low=funnel.get("low_confidence_genuine_forward_sources") or {}
    fcounts=forward_health.get("counts") or {}
    genuine_rules=int(fcounts.get("genuine_forward_rules") or 0)
    maturity_state="not_started" if genuine_rules==0 else ("started" if forward else "awaiting_first_baseline")

    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "evaluation_spec_version":events.get("spec_version"),
        "scoring_engine_version":events.get("scoring_engine_version"),
        "evidence_layers":{
            "legacy_observational_archive":{
                "count":int(co_counts.get("events_total") or 0),
                "label":"历史观察归档",
                "description":"历史/迁移事件，仅供复盘和方法线索，不参与 Promotion。"
            },
            "forward_evidence_candidates":{
                "count":len(forward),
                "scoreable_now":len(scoreable),
                "forward_rules_observed":int(fam_counts.get("forward_rules_observed") or 0),
                "label":"Forward 证据候选",
                "description":"在真实收录时间之后形成的 point-in-time 事件；未成熟前不代表方法有效。"
            },
            "mature_scoreable_evidence":{
                "event_count_20d":len(mature20),
                "event_count_60d":len(mature60),
                "effective_units_20d":int(rd.get("mature_20_effective_units") or 0),
                "effective_units_60d":int(rd.get("mature_60_effective_units") or 0),
                "label":"成熟可评分证据",
                "description":"满足 point-in-time、价格来源、语义与成熟度要求后进入统计检验的证据。"
            }
        },
        "promotion":{
            "families_passed":int(promo_counts.get("passed") or 0),
            "families_reviewable":int(promo_counts.get("statistical_criteria_passed") or 0),
            "production_effect":"none"
        },
        "source_rule_funnel":{
            "schema_version":funnel.get("schema_version"),
            "status":funnel.get("status") or "unavailable",
            "generated_at":funnel.get("generated_at"),
            "new_sources_total":int(funnel.get("new_sources_total") or 0),
            "terminal_reason_counts":funnel.get("terminal_reason_counts") or {},
            "terminal_reason_share":funnel.get("terminal_reason_share") or {},
            "conservation":funnel.get("conservation") or {},
            "downstream":{
                "operations_total":int(funnel_down.get("operations_total") or 0),
                "propositions_total":int(funnel_down.get("propositions_total") or 0),
                "new_forward_rules_total":int(funnel_down.get("new_forward_rules_total") or 0),
                "independent_authors":int(funnel_down.get("independent_authors") or 0),
                "largest_author_rule_share":funnel_down.get("largest_author_rule_share"),
                "cumulative_forward_rules":int(funnel_down.get("cumulative_forward_rules") or 0),
                "cumulative_forward_authors":int(funnel_down.get("cumulative_forward_authors") or 0),
                "cumulative_largest_author_rule_share":funnel_down.get("cumulative_largest_author_rule_share"),
                "admission_sources_with_operations":funnel_down.get("admission_sources_with_operations") or {},
                "no_operations_context_split":funnel_down.get("no_operations_context_split") or {},
            },
            "low_confidence_genuine_forward_sources":{
                "new":int(funnel_low.get("new") or 0),
                "cumulative":int(funnel_low.get("cumulative") or 0),
                "review_required":bool(funnel_low.get("review_required")),
            },
            "non_gating":True,
            "result_blind":True,
        },
        "maturity_clock":{
            "status":maturity_state,
            "genuine_forward_rules":genuine_rules,
            "first_eligible_baseline_timestamp_utc":min(
                [str(e.get("baseline_timestamp_utc")) for e in forward if e.get("baseline_timestamp_utc")],
                default=None
            ),
            "mature_20_effective_units":int(rd.get("mature_20_effective_units") or 0),
            "mature_60_effective_units":int(rd.get("mature_60_effective_units") or 0),
        },
        "forward_intake_health":{
            "status":forward_health.get("status") or "unknown",
            "integrity_pass":bool(forward_health.get("integrity_pass")),
            "forward_path_observed":bool(forward_health.get("forward_path_observed")),
            "first_scoreable_forward_observed":bool(forward_health.get("first_scoreable_forward_observed")),
            "blockers":forward_health.get("blockers") or []
        },
        "readiness":{
            "ready_for_v616":bool(readiness.get("ready_for_v616")),
            "blockers":readiness.get("blockers") or []
        },
        "guardrails":[
            "Legacy observational archive counts are not research sample counts.",
            "Forward candidates are not mature evidence.",
            "Method Memory and Source Outcome remain descriptive/legacy views and cannot override current Evaluation Spec Promotion evidence.",
            "This public summary contains no private positions or account data.",
            "Source-to-Rule funnel is diagnostic and cannot feed Promotion, Readiness, Planner, Agent, or trading decisions."
        ]
    }

def main():
    out=build(
        load(EVENTS,{}),
        load(COEX,{}),
        load(READINESS,{}),
        load(FAMILY,{}),
        load(PROMOTION,{}),
        load(FORWARD_HEALTH,{}),
        load(FUNNEL,{})
    )
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "spec":out["evaluation_spec_version"],
        "legacy":out["evidence_layers"]["legacy_observational_archive"]["count"],
        "forward":out["evidence_layers"]["forward_evidence_candidates"]["count"],
        "mature20":out["evidence_layers"]["mature_scoreable_evidence"]["event_count_20d"],
        "mature60":out["evidence_layers"]["mature_scoreable_evidence"]["event_count_60d"],
    },ensure_ascii=False))

if __name__=="__main__":
    main()
