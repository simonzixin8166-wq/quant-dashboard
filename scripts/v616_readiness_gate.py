#!/usr/bin/env python3
"""V6.15.8c operational V6.16 Readiness Gate."""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research"/"specs"/"v616_readiness_spec.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"
SOURCE=ROOT/"research"/"store"/"source_store.json"
CONTROLS=ROOT/"research"/"reports"/"statistical_controls.json"
BOUNDARY=ROOT/"research"/"audit"/"step_boundary_log.json"
COMPONENTS=ROOT/"research"/"component_manifest.json"
OUT=ROOT/"research"/"reports"/"v616_readiness_gate.json"
VERSION="6.15.8c"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def family_map(families):
    latest_hash=families.get("definition_hash")
    out={}
    for a in families.get("assignments") or []:
        if a.get("active") and a.get("definition_hash")==latest_hash:
            out[a.get("rule_id")]=a.get("family_id")
    return out

def clean_boundary_runs(boundary):
    grouped=defaultdict(list)
    for r in boundary.get("records") or []:
        run=str(r.get("workflow_run_id") or "")
        if not run or run=="local":continue
        grouped[run].append(r)
    clean=0
    for rows in grouped.values():
        if rows and all(x.get("production_boundary_unchanged") and x.get("research_only_worktree") for x in rows):
            clean+=1
    return clean

def mature_counts(events,families):
    r2f=family_map(families)
    out={"20":0,"60":0,"families20":set(),"families60":set()}
    for e in events.get("events") or []:
        if not e.get("scoreable") or e.get("point_in_time_status")!="eligible":
            continue
        fid=r2f.get(e.get("rule_id"))
        if not fid:continue
        for h in ("20","60"):
            if (e.get("scores") or {}).get(h):
                out[h]+=1
                out["families"+h].add(fid)
    return {
        "mature_20":out["20"],
        "mature_60":out["60"],
        "families_with_20":len(out["families20"]),
        "families_with_60":len(out["families60"]),
    }

def build(spec,events,families,source,controls,boundary,components):
    req=spec.get("requirements") or {}
    source_ok=len(source.get("records") or [])>=int(source.get("source_window_reported_total") or 0)
    conservation=bool((events.get("counts") or {}).get("conservation_ok"))
    control_names=req.get("statistical_controls_required") or []
    control_map=controls.get("controls") or {}
    control_ok=bool(controls.get("all_pass")) and all((control_map.get(k) or {}).get("pass") for k in control_names)
    clean_runs=clean_boundary_runs(boundary)
    maturity=mature_counts(events,families)
    component_ok=(components.get("counts") or {}).get("missing_code_hashes",1)==0 and (components.get("counts") or {}).get("missing_required_artifact_hashes",1)==0

    conditions={
        "eventscore_conservation":conservation,
        "source_store_full_coverage":source_ok,
        "statistical_controls":control_ok,
        "production_boundary_clean_runs":clean_runs>=int(req.get("production_boundary_clean_workflow_runs_min") or 0),
        "point_in_time_mature_20_events":maturity["mature_20"]>=int(req.get("point_in_time_mature_20_events_min") or 0),
        "point_in_time_mature_60_events":maturity["mature_60"]>=int(req.get("point_in_time_mature_60_events_min") or 0),
        "families_with_mature_20":maturity["families_with_20"]>=int(req.get("families_with_mature_20_min") or 0),
        "families_with_mature_60":maturity["families_with_60"]>=int(req.get("families_with_mature_60_min") or 0),
        "component_manifest_complete":component_ok,
    }
    blockers=[k for k,v in conditions.items() if not v]
    max_blockers=int(req.get("unresolved_integrity_blockers_max") or 0)
    ready=all(conditions.values()) and len(blockers)<=max_blockers
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "readiness_spec_version":spec.get("readiness_spec_version"),
        "ready_for_v616":ready,
        "promotion_pass_required":False,
        "observed":{
            "clean_boundary_workflow_runs":clean_runs,
            **maturity,
            "source_store_records":len(source.get("records") or []),
            "source_store_reported_total":source.get("source_window_reported_total"),
        },
        "conditions":conditions,
        "blockers":blockers,
        "guardrails":[
            "This gate measures pipeline readiness only; it does not validate investment effectiveness.",
            "No Promotion Gate pass is required.",
            "Passing this gate authorizes only a review of whether to begin V6.16."
        ],
    }

def main():
    out=build(load(SPEC,{}),load(EVENTS,{}),load(FAMILIES,{}),load(SOURCE,{}),load(CONTROLS,{}),load(BOUNDARY,{}),load(COMPONENTS,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"ready_for_v616":out["ready_for_v616"],"blockers":out["blockers"],"observed":out["observed"]},ensure_ascii=False))

if __name__=="__main__":main()
