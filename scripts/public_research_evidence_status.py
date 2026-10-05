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
OUT=ROOT/"docs"/"research"/"evidence_status.json"
VERSION="1.0"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def build(events, coexistence, readiness, family, promotion, forward_health):
    rows=events.get("events") or []
    forward=[e for e in rows if e.get("point_in_time_status")=="eligible"]
    scoreable=[e for e in forward if e.get("scoreable")]
    mature20=[e for e in scoreable if (e.get("scores") or {}).get("20")]
    mature60=[e for e in scoreable if (e.get("scores") or {}).get("60")]
    co_counts=coexistence.get("counts") or {}
    rd=readiness.get("observed") or {}
    fam_counts=family.get("counts") or {}
    promo_counts=promotion.get("counts") or {}

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
            "Method Memory and Source Outcome remain descriptive/legacy views and cannot override Spec 1.5 Promotion evidence.",
            "This public summary contains no private positions or account data."
        ]
    }

def main():
    out=build(
        load(EVENTS,{}),
        load(COEX,{}),
        load(READINESS,{}),
        load(FAMILY,{}),
        load(PROMOTION,{}),
        load(FORWARD_HEALTH,{})
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
