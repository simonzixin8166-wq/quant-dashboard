import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_forward_intake_health import build

spec={"spec_version":"1.5","definitions":{"rule_family_definition_hash":"defhash"}}
base_store={"records":[{"source_key":"old","ingest_type":"initial_migration","record":{"id":"old"}}]}
base_rules={"rules":[{"rule_id":"r0","source_id":"old","author":"a","active":True}]}
base_families={"assignments":[{"rule_id":"r0","definition_hash":"defhash","active":True}]}
base_events={"scoring_engine_version":"event_score@6.15.8j","events":[{"event_id":"e0","rule_id":"r0","point_in_time_status":"historical_pre_ingest","scoreable":False}]}

waiting=build(base_store,base_rules,base_families,base_events,spec,now="2026-10-05T00:00:00Z")
assert waiting["integrity_pass"] is True
assert waiting["status"]=="waiting_for_first_genuine_forward_rule"
assert waiting["counts"]["genuine_forward_rules"]==0

live_store={"records":base_store["records"]+[{"source_key":"s1","ingest_type":"live_ingest","record":{"id":"s1"}}]}
live_rules={"rules":base_rules["rules"]+[{"rule_id":"r1","source_id":"s1","author":"new-author","active":True}]}
live_families={"assignments":base_families["assignments"]+[{"rule_id":"r1","definition_hash":"defhash","active":True}]}
live_events={"scoring_engine_version":"event_score@6.15.8j","events":base_events["events"]+[{
 "event_id":"e1","rule_id":"r1","point_in_time_status":"eligible","scoreable":True,"primary_exclusion_reason":None
}]}
healthy=build(live_store,live_rules,live_families,live_events,spec,now="2026-10-06T00:00:00Z")
assert healthy["integrity_pass"] is True
assert healthy["status"]=="healthy_forward_intake_observed"
assert healthy["forward_path_observed"] is True
assert healthy["first_scoreable_forward_observed"] is True
assert healthy["counts"]["genuine_forward_rules"]==1
assert healthy["counts"]["point_in_time_eligible_events"]==1

broken=build(live_store,live_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert broken["integrity_pass"] is False
assert "live_rule_missing_current_family_assignment" in broken["blockers"]
assert "live_rule_missing_eventscore_event" in broken["blockers"]

bad_event={"scoring_engine_version":"event_score@6.15.8j","events":base_events["events"]+[{
 "event_id":"e1","rule_id":"r1","point_in_time_status":"historical_pre_ingest","scoreable":False,
 "primary_exclusion_reason":"non_point_in_time_source"
}]}
bad=build(live_store,live_rules,live_families,bad_event,spec,now="2026-10-06T00:00:00Z")
assert bad["integrity_pass"] is False
assert "live_rule_event_not_point_in_time_eligible" in bad["blockers"]
print("PASS V6.15 forward intake health guard")
