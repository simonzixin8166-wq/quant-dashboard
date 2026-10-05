#!/usr/bin/env python3
"""Result-blind V6.16 readiness attainability forecast."""
from __future__ import annotations
import json
from datetime import datetime,timezone,date,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
READINESS=ROOT/"research"/"reports"/"v616_readiness_gate.json"
READINESS_SPEC=ROOT/"research"/"specs"/"v616_readiness_spec.json"
FEASIBILITY=ROOT/"research"/"reports"/"family_feasibility.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
BOUNDARY=ROOT/"research"/"audit"/"step_boundary_log.json"
OUT=ROOT/"research"/"reports"/"v616_readiness_forecast.json"
VERSION="6.15.8g"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def parse_dt(v):
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception:return None

def add_business_days(start,n):
    d=start;count=0
    while count<int(n):
        d+=timedelta(days=1)
        if d.weekday()<5:count+=1
    return d

def build(readiness,spec,feas,events,boundary,now=None):
    now=now or datetime.now(timezone.utc)
    clean_dates=[]
    for r in boundary.get("records") or []:
        if str(r.get("workflow_run_id") or "")=="local":continue
        if not (r.get("production_boundary_unchanged") and r.get("research_only_worktree") and r.get("evidence_lock_unchanged",True)):
            continue
        dt=parse_dt(r.get("completed_at"))
        if dt:clean_dates.append(dt)
    first_clean=min(clean_dates) if clean_dates else None
    span_req=int((spec.get("requirements") or {}).get("production_boundary_clean_span_days_min") or 0)
    clean_span_earliest=(first_clean.date()+timedelta(days=span_req)).isoformat() if first_clean else None

    eligible=[e for e in events.get("events") or [] if e.get("point_in_time_status")=="eligible" and e.get("scoreable")]
    first_eligible_dates=[]
    for e in eligible:
        try:first_eligible_dates.append(date.fromisoformat(str(e.get("baseline_date"))[:10]))
        except Exception:pass
    first_eligible=min(first_eligible_dates) if first_eligible_dates else None

    theoretical_start=first_eligible or date(2026,10,4)
    maturity_lower_bounds={
        "20d":add_business_days(theoretical_start,20).isoformat(),
        "60d":add_business_days(theoretical_start,60).isoformat(),
    }

    rate=(feas.get("forward_rule_rate") or {})
    rate_estimable=rate.get("status")=="estimable" and rate.get("weekly_forward_rule_rate")
    eta_status="not_estimable_until_forward_intake_rate_exists"
    if first_eligible and rate_estimable:
        eta_status="partially_estimable_but_overlap_author_diversity_still_required"

    blockers=readiness.get("blockers") or []
    return {
        "version":VERSION,
        "generated_at":now.isoformat(),
        "readiness_spec_version":spec.get("readiness_spec_version"),
        "ready_for_v616":bool(readiness.get("ready_for_v616")),
        "eta_status":eta_status,
        "observed":readiness.get("observed") or {},
        "blockers":blockers,
        "clean_run_span":{
            "first_clean_run_at":first_clean.isoformat() if first_clean else None,
            "required_span_days":span_req,
            "calendar_earliest_span_satisfied":clean_span_earliest,
            "note":"This is a calendar lower bound, not a guarantee that all other readiness conditions will be met."
        },
        "forward_evidence":{
            "scoreable_point_in_time_events_now":len(eligible),
            "first_scoreable_point_in_time_baseline":first_eligible.isoformat() if first_eligible else None,
            "theoretical_maturity_lower_bounds":maturity_lower_bounds,
            "lower_bound_basis":"first real scoreable point-in-time baseline if available; otherwise 2026-10-04 is shown only as a mathematical foundation lower bound",
            "warning":"Without real forward event generation rate and overlap-connected cluster formation, no honest completion date can be predicted."
        },
        "rule_intake_rate":rate,
        "family_author_diversity":{
            "families_meeting_author_threshold":(feas.get("counts") or {}).get("families_meeting_author_threshold"),
            "max_unique_authors_in_one_family":(feas.get("counts") or {}).get("max_unique_authors_in_one_family"),
            "next_structural_review_trigger":(feas.get("assessment") or {}).get("next_structural_review_trigger"),
        },
        "guardrails":[
            "Forecasting uses dates, counts and structural intake only; never returns, lift, pass rates or named-method performance.",
            "Theoretical maturity dates are lower bounds, not promises.",
            "Readiness requirements cannot be relaxed to make the ETA earlier.",
            "V6.16 remains frozen until the actual Readiness Gate passes and a separate human review occurs."
        ],
    }

def main():
    out=build(load(READINESS,{}),load(READINESS_SPEC,{}),load(FEASIBILITY,{}),load(EVENTS,{}),load(BOUNDARY,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"eta_status":out["eta_status"],"ready_for_v616":out["ready_for_v616"],"blockers":out["blockers"]},ensure_ascii=False))

if __name__=="__main__":main()
