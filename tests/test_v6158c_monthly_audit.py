import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_monthly_evidence_audit import build

data={
 "source":{"source_window_reported_total":3,"legacy_reported_total":3,"visible_window_size":2,"full_ingest_size":3,
           "upstream_reconciliation":{"upstream_raw_records":4,"eligible_raw_records":4,"normalized_unique_records":3,"duplicates_removed":1,"excluded_missing_identity":0,"reconciliation_ok":True},
           "source_accounting":{"current_upstream_records":3,"current_ingested_unique_records":3,"retained_historical_records":0,"current_ingest_complete":True},"records":[1,2,3]},
 "events":{"counts":{"events":2,"scoreable":1,"conservation_ok":True,"primary_exclusion":{"missing_rule_id":1}},
           "events":[{"event_id":"e1","scoreable":True},{"event_id":"e2","scoreable":False,"primary_exclusion_reason":"missing_rule_id"}]},
 "families":{"counts":{"active_families":1}},
 "scorecards":{"counts":{"reviewable":0}},
 "promotion":{"counts":{"passed":0}},
 "controls":{"all_pass":True},
 "readiness":{"ready_for_v616":False,"blockers":["point_in_time_mature_60_events"]},
 "boundary":{"records":[{"production_boundary_unchanged":True,"research_only_worktree":True}]},
 "cache":{"counts":{"symbols":2,"events":3}},
 "components":{"counts":{"missing_code_hashes":0,"missing_required_artifact_hashes":0}},
 "forward_intake":{"integrity_pass":True,"status":"waiting_for_first_genuine_forward_rule","forward_path_observed":False,"first_scoreable_forward_observed":False,"counts":{"genuine_forward_rules":0},"blockers":[]},
}
out=build(data,datetime(2026,10,4,tzinfo=timezone.utc))
assert out["audit_month"]=="2026-10"
assert out["all_integrity_checks_pass"] is True
assert out["eventscore"]["events"]==2
assert out["source_store"]["persistent_records"]==3
assert out["source_store"]["current_full_ingest_records"]==3
assert out["source_store"]["current_upstream_records"]==3
assert out["readiness"]["ready_for_v616"] is False
assert out["checks"]["forward_intake_integrity"] is True
assert out["forward_intake"]["status"]=="waiting_for_first_genuine_forward_rule"

# Negative integrity injection must make the audit fail.
bad=dict(data)
bad["events"]={"counts":{"events":2,"scoreable":0,"conservation_ok":False,"primary_exclusion":{}},
               "events":[{"event_id":"e","scoreable":False,"primary_exclusion_reason":None}]}
out2=build(bad,datetime(2026,10,4,tzinfo=timezone.utc))
assert out2["all_integrity_checks_pass"] is False
assert out2["checks"]["event_conservation"] is False
assert out2["checks"]["no_reasonless_rejections"] is False

bad_source=dict(data)
bad_source["source"]={"source_window_reported_total":3,"legacy_reported_total":3,"visible_window_size":2,"full_ingest_size":2,
"upstream_reconciliation":{"upstream_raw_records":3,"eligible_raw_records":3,"normalized_unique_records":3,"duplicates_removed":0,"excluded_missing_identity":0,"reconciliation_ok":True},
"source_accounting":{"current_upstream_records":3,"current_ingested_unique_records":2,"retained_historical_records":8,"current_ingest_complete":False},"records":[1,2,3,4,5,6,7,8,9,10]}
out3=build(bad_source,datetime(2026,10,4,tzinfo=timezone.utc))
assert out3["all_integrity_checks_pass"] is False
assert out3["checks"]["source_store_full_coverage"] is False
assert out3["source_store"]["persistent_records"]==10
assert out3["source_store"]["current_full_ingest_records"]==2

workflow=(ROOT/".github/workflows/monthly-evidence-audit.yml").read_text(encoding="utf-8")
assert "cron: '30 22 1 * *'" in workflow
assert "contents: read" in workflow
assert "contents: write" in workflow
assert "monthly_integrity_audit" in workflow
print("PASS V6.15.8h monthly audit current-ingest completeness / fixed cadence / hard isolation")


bad_forward=dict(data)
bad_forward["forward_intake"]={"integrity_pass":False,"status":"forward_intake_integrity_failure","forward_path_observed":True,"first_scoreable_forward_observed":False,"counts":{"genuine_forward_rules":1},"blockers":["live_rule_missing_eventscore_event"]}
out4=build(bad_forward,datetime(2026,10,4,tzinfo=timezone.utc))
assert out4["all_integrity_checks_pass"] is False
assert out4["checks"]["forward_intake_integrity"] is False
