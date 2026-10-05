#!/usr/bin/env python3
"""V6.15.8c operational V6.16 Readiness Gate."""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_dependence_clusters import overlap_connected_clusters,assert_non_overlapping
SPEC=ROOT/"research"/"specs"/"v616_readiness_spec.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"
SOURCE=ROOT/"research"/"store"/"source_store.json"
CONTROLS=ROOT/"research"/"reports"/"statistical_controls.json"
BOUNDARY=ROOT/"research"/"audit"/"step_boundary_log.json"
COMPONENTS=ROOT/"research"/"component_manifest.json"
OUT=ROOT/"research"/"reports"/"v616_readiness_gate.json"
VERSION="6.15.8i"

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
    clean_rows=[]
    for run,rows in grouped.items():
        if rows and all(x.get("production_boundary_unchanged") and x.get("research_only_worktree") and x.get("evidence_lock_unchanged",True) for x in rows):
            dates=[]
            for x in rows:
                try:dates.append(datetime.fromisoformat(str(x.get("completed_at")).replace("Z","+00:00")))
                except Exception:pass
            clean_rows.append({"run":run,"when":min(dates) if dates else None})
    dated=[x["when"] for x in clean_rows if x["when"] is not None]
    span=(max(dated)-min(dated)).days if len(dated)>=2 else 0
    return {"count":len(clean_rows),"span_days":span}

def mature_counts(events,families):
    r2f=family_map(families)
    units={"20":set(),"60":set()}
    fams={"20":set(),"60":set()}
    eligible=[
        e for e in (events.get("events") or [])
        if e.get("scoreable") and e.get("point_in_time_status")=="eligible" and r2f.get(e.get("rule_id"))
    ]
    for h in ("20","60"):
        cluster_map,meta=overlap_connected_clusters(eligible,int(h),require_lift=False)
        if not assert_non_overlapping(meta):
            raise AssertionError(f"readiness clusters overlap for horizon {h}")
        for e in eligible:
            if not (e.get("scores") or {}).get(h):
                continue
            cluster=cluster_map.get(str(e.get("event_id") or ""))
            if cluster is None:
                continue
            sym=str(e.get("symbol") or "unknown")
            units[h].add((sym,cluster))
            fams[h].add(r2f.get(e.get("rule_id")))
    return {
        "mature_20_effective_units":len(units["20"]),
        "mature_60_effective_units":len(units["60"]),
        "families_with_20":len(fams["20"]),
        "families_with_60":len(fams["60"]),
    }

def build(spec,events,families,source,controls,boundary,components):
    req=spec.get("requirements") or {}
    current_ingest=int(source.get("full_ingest_size") if source.get("full_ingest_size") is not None else len(source.get("records") or []))
    accounting=source.get("source_accounting") or {}
    reconciliation=source.get("upstream_reconciliation") or {}
    current_upstream=int(accounting.get("current_upstream_records") if accounting.get("current_upstream_records") is not None else current_ingest)
    source_ok=bool(
        accounting.get("current_ingest_complete")
        and reconciliation.get("reconciliation_ok",True)
        and current_ingest==current_upstream
    )
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
        "production_boundary_clean_runs":clean_runs["count"]>=int(req.get("production_boundary_clean_workflow_runs_min") or 0),
        "production_boundary_clean_span":clean_runs["span_days"]>=int(req.get("production_boundary_clean_span_days_min") or 0),
        "point_in_time_mature_20_effective_units":maturity["mature_20_effective_units"]>=int(req.get("point_in_time_mature_20_effective_units_min") or 0),
        "point_in_time_mature_60_effective_units":maturity["mature_60_effective_units"]>=int(req.get("point_in_time_mature_60_effective_units_min") or 0),
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
            "clean_boundary_workflow_runs":clean_runs["count"],
            "clean_boundary_span_days":clean_runs["span_days"],
            **maturity,
            "source_store_persistent_records":len(source.get("records") or []),
            "source_store_current_full_ingest_records":current_ingest,
            "source_store_current_upstream_records":current_upstream,
            "source_store_retained_historical_records":accounting.get("retained_historical_records"),
            "source_store_legacy_reported_total":source.get("legacy_reported_total",source.get("source_window_reported_total")),
            "source_store_upstream_raw_records":reconciliation.get("upstream_raw_records"),
            "source_store_upstream_duplicates_removed":reconciliation.get("duplicates_removed"),
            "source_store_upstream_excluded":reconciliation.get("excluded_missing_identity"),
        },
        "conditions":conditions,
        "blockers":blockers,
        "guardrails":[
            "This gate measures pipeline readiness only; it does not validate investment effectiveness.",
            "Source Store completeness is judged from the same-run raw→eligible→deduplicated reconciliation and current full ingest; legacy reported totals and append-only history are non-gating.",
            "Maturity uses the same overlap-connected realized-horizon clusters as Family Scorecards.",
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
