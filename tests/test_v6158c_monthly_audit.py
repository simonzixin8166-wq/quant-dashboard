import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_monthly_evidence_audit import build

data={
 "source":{"source_window_reported_total":3,"visible_window_size":2,"records":[1,2,3]},
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
}
out=build(data,datetime(2026,10,4,tzinfo=timezone.utc))
assert out["audit_month"]=="2026-10"
assert out["all_integrity_checks_pass"] is True
assert out["eventscore"]["events"]==2
assert out["source_store"]["records"]==3
assert out["readiness"]["ready_for_v616"] is False

# Negative integrity injection must make the audit fail.
bad=dict(data)
bad["events"]={"counts":{"events":2,"scoreable":0,"conservation_ok":False,"primary_exclusion":{}},
               "events":[{"event_id":"e","scoreable":False,"primary_exclusion_reason":None}]}
out2=build(bad,datetime(2026,10,4,tzinfo=timezone.utc))
assert out2["all_integrity_checks_pass"] is False
assert out2["checks"]["event_conservation"] is False
assert out2["checks"]["no_reasonless_rejections"] is False

workflow=(ROOT/".github/workflows/monthly-evidence-audit.yml").read_text(encoding="utf-8")
assert "cron: '30 22 1 * *'" in workflow
assert "contents: read" in workflow
assert "contents: write" in workflow
assert "monthly_integrity_audit" in workflow
print("PASS V6.15.8c monthly evidence audit / fixed cadence / hard isolation")
