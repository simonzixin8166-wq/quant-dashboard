#!/usr/bin/env python3
"""V6.15.8c monthly evidence audit."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATHS={
 "source":ROOT/"research/store/source_store.json",
 "events":ROOT/"research/events/event_scores_v1.json",
 "families":ROOT/"research/registry/rule_families.json",
 "scorecards":ROOT/"research/reports/family_scorecards.json",
 "promotion":ROOT/"research/reports/promotion_gate.json",
 "controls":ROOT/"research/reports/statistical_controls.json",
 "readiness":ROOT/"research/reports/v616_readiness_gate.json",
 "boundary":ROOT/"research/audit/step_boundary_log.json",
 "cache":ROOT/"research/audit/v615_cache_only_stooq_coverage.json",
 "components":ROOT/"research/component_manifest.json",
}
OUT=ROOT/"research"/"reports"/"monthly_evidence_audit.json"
HIST=ROOT/"research"/"reports"/"monthly"
VERSION="6.15.8d"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(data,now=None):
    now=now or datetime.now(timezone.utc)
    source=data["source"];events=data["events"];families=data["families"]
    score=data["scorecards"];promotion=data["promotion"];controls=data["controls"]
    readiness=data["readiness"];boundary=data["boundary"];cache=data["cache"];components=data["components"]
    exclusions=(events.get("counts") or {}).get("primary_exclusion") or {}
    boundary_failures=[r for r in boundary.get("records") or [] if r.get("production_boundary_unchanged") is False or r.get("research_only_worktree") is False or r.get("evidence_lock_unchanged") is False]
    checks={
        "event_conservation":bool((events.get("counts") or {}).get("conservation_ok")),
        "no_reasonless_rejections":all(e.get("scoreable") or e.get("primary_exclusion_reason") for e in events.get("events") or []),
        "source_store_full_coverage":len(source.get("records") or [])>=int(source.get("source_window_reported_total") or 0),
        "boundary_no_failures":len(boundary_failures)==0,
        "statistical_controls_pass":bool(controls.get("all_pass")),
        "component_manifest_complete":(components.get("counts") or {}).get("missing_code_hashes",1)==0 and (components.get("counts") or {}).get("missing_required_artifact_hashes",1)==0,
    }
    return {
        "version":VERSION,
        "generated_at":now.isoformat(),
        "audit_month":now.strftime("%Y-%m"),
        "all_integrity_checks_pass":all(checks.values()),
        "checks":checks,
        "eventscore":{
            "events":(events.get("counts") or {}).get("events"),
            "scoreable":(events.get("counts") or {}).get("scoreable"),
            "primary_exclusion":exclusions,
        },
        "source_store":{
            "records":len(source.get("records") or []),
            "reported_total":source.get("source_window_reported_total"),
            "visible_window":source.get("visible_window_size"),
        },
        "families":{
            "active_families":(families.get("counts") or {}).get("active_families"),
            "reviewable":(score.get("counts") or {}).get("reviewable"),
            "promotion_passed":(promotion.get("counts") or {}).get("passed"),
        },
        "cache_coverage":cache.get("counts") or {},
        "readiness":{
            "ready_for_v616":readiness.get("ready_for_v616"),
            "blockers":readiness.get("blockers") or [],
        },
        "boundary_failures":len(boundary_failures),
        "guardrails":[
            "Monthly audit is read-only with respect to production state.",
            "Audit findings never change thresholds or Promotion criteria.",
            "Automatic operation does not replace periodic integrity review."
        ],
    }

def main():
    data={k:load(p,{}) for k,p in PATHS.items()}
    out=build(data)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    HIST.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    (HIST/f"{out['audit_month']}.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"month":out["audit_month"],"all_integrity_checks_pass":out["all_integrity_checks_pass"],"ready_for_v616":out["readiness"]["ready_for_v616"]},ensure_ascii=False))

if __name__=="__main__":main()
