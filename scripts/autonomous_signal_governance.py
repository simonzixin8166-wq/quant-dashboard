#!/usr/bin/env python3
"""Governed autonomous-signal bridge.

Publishes a small public contract telling the UI whether learned research is
allowed to affect production actions. It never promotes a method itself.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROMOTION=ROOT/"research"/"reports"/"promotion_gate.json"
EVIDENCE=ROOT/"docs"/"research"/"evidence_status.json"
OUT=ROOT/"docs"/"research"/"signal_governance.json"
VERSION="1.0"

def load(path, default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def build(promotion,evidence):
    rows=promotion.get("results") or []
    promoted=[
        {
            "family_id":r.get("family_id"),
            "member_rule_ids":r.get("member_rule_ids") or [],
            "review_date":r.get("review_date"),
        }
        for r in rows
        if r.get("passed") is True and r.get("production_effect")=="active"
    ]
    ev_promotion=evidence.get("promotion") or {}
    effect="active" if promoted and ev_promotion.get("production_effect")=="active" else "none"
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "formal_app_version":"6.9.0",
        "decision_authority":"today_cockpit",
        "learned_production_effect":effect,
        "promoted_families":promoted if effect=="active" else [],
        "action_vocabulary":[
            "WATCH","EARLY_ENTRY","CONFIRMED_ENTRY","HOLD","NO_ADD","REDUCE","EXIT"
        ],
        "policy":{
            "learn_autonomously":True,
            "candidate_rules_allowed":True,
            "shadow_validation_allowed":True,
            "production_requires_promotion_gate":True,
            "human_approval_required_for_protected_rule_changes":True,
            "automatic_trading":False,
        },
        "protected_rules":[
            "TQQQ Hard Exit",
            "Core ETF tiers",
            "LEAPS single <=1%",
            "LEAPS total <=3%",
            "Options no auto trading",
        ],
        "guardrails":[
            "Historical/backfill evidence cannot become genuine Forward evidence by relabeling.",
            "A learned method cannot affect production actions unless Promotion Gate explicitly passes and production_effect is active.",
            "Data Trust and Today Cockpit Decision Authority remain higher priority than learned overlays.",
            "No signal places orders or chooses share/contract quantity automatically.",
        ],
    }

def main():
    out=build(load(PROMOTION,{}),load(EVIDENCE,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"learned_production_effect":out["learned_production_effect"],"promoted_families":len(out["promoted_families"])},ensure_ascii=False))

if __name__=="__main__":main()
