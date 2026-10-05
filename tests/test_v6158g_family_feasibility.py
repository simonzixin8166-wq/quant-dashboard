import sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

from v615_family_feasibility import build as build_feasibility
from v616_readiness_forecast import build as build_forecast

spec={
 "spec_version":"1.4",
 "definitions":{"rule_family_definition_hash":"h"},
 "thresholds":{"independent_authors_min":3}
}
rules={"rules":[
 {"rule_id":"r1","active":True,"author":"a","source_id":"s1","first_seen_at":"2026-10-04T00:00:00+00:00"},
 {"rule_id":"r2","active":True,"author":"b","source_id":"s2","first_seen_at":"2026-10-20T00:00:00+00:00"},
 {"rule_id":"r3","active":True,"author":"c","source_id":"s3","first_seen_at":"2026-10-25T00:00:00+00:00"},
]}
families={"assignments":[
 {"rule_id":"r1","family_id":"f","definition_hash":"h","active":True,"family_key":{"direction":"bullish"}},
 {"rule_id":"r2","family_id":"f","definition_hash":"h","active":True,"family_key":{"direction":"bullish"}},
 {"rule_id":"r3","family_id":"f","definition_hash":"h","active":True,"family_key":{"direction":"bullish"}},
]}
source={"records":[
 {"source_key":"s1","ingest_type":"initial_migration","record":{"id":"s1"}},
 {"source_key":"s2","ingest_type":"forward_ingest","record":{"id":"s2"}},
 {"source_key":"s3","ingest_type":"forward_ingest","record":{"id":"s3"}},
]}
feas=build_feasibility(rules,families,source,spec)
assert feas["result_blind"] is True
assert feas["counts"]["active_families"]==1
assert feas["counts"]["unique_authors_across_active_rules"]==3
assert feas["counts"]["families_meeting_author_threshold"]==1
assert feas["families"][0]["unique_authors"]==3
assert feas["families"][0]["authors_needed_for_threshold"]==0
assert feas["counts"]["forward_rules_observed"]==2
assert feas["forward_rule_rate"]["status"]=="insufficient_forward_history"  # only 5 longitudinal days
blob=str(feas)
for forbidden in ["unconditional_lift","direction_adjusted_return","win_rate","promotion_passed"]:
    assert forbidden not in blob

readiness={
 "ready_for_v616":False,
 "observed":{"clean_boundary_workflow_runs":2},
 "blockers":["production_boundary_clean_span","point_in_time_mature_20_effective_units"]
}
rspec={"readiness_spec_version":"1.2","requirements":{"production_boundary_clean_span_days_min":14}}
events={"events":[]}
boundary={"records":[
 {"workflow_run_id":"1","completed_at":"2026-10-04T12:00:00+00:00","production_boundary_unchanged":True,"research_only_worktree":True,"evidence_lock_unchanged":True},
 {"workflow_run_id":"2","completed_at":"2026-10-05T12:00:00+00:00","production_boundary_unchanged":True,"research_only_worktree":True,"evidence_lock_unchanged":True},
]}
forecast=build_forecast(
 readiness,rspec,feas,events,boundary,
 now=datetime(2026,10,5,tzinfo=timezone.utc)
)
assert forecast["ready_for_v616"] is False
assert forecast["eta_status"]=="not_estimable_until_forward_intake_rate_exists"
assert forecast["clean_run_span"]["calendar_earliest_span_satisfied"]=="2026-10-18"
assert forecast["forward_evidence"]["scoreable_point_in_time_events_now"]==0
assert forecast["forward_evidence"]["theoretical_maturity_lower_bounds"]["20d"]
assert forecast["forward_evidence"]["theoretical_maturity_lower_bounds"]["60d"]
assert "no honest completion date" in forecast["forward_evidence"]["warning"]
print("PASS V6.15.8g structural family feasibility / result-blind readiness forecast")
