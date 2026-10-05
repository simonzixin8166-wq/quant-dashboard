import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_forward_intake_health import build

spec={"spec_version":"1.7","definitions":{"rule_family_definition_hash":"defhash","point_in_time_eligibility":{"evidence_foundation_start_utc":"2026-10-04T00:00:00+00:00","source_admission":{"genuine_forward_required_class":"genuine_forward"}}}}
base_store={"records":[{"source_key":"old","ingest_type":"initial_migration","record":{"id":"old"}}]}
base_rules={"rules":[{"rule_id":"r0","source_id":"old","author":"a","active":True}]}
base_families={"assignments":[{"rule_id":"r0","definition_hash":"defhash","active":True}]}
base_events={"scoring_engine_version":"event_score@6.15.8j","events":[{"event_id":"e0","rule_id":"r0","point_in_time_status":"historical_pre_ingest","scoreable":False}]}

waiting=build(base_store,base_rules,base_families,base_events,spec,now="2026-10-05T00:00:00Z")
assert waiting["integrity_pass"] is True
assert waiting["status"]=="waiting_for_first_genuine_forward_rule"
assert waiting["counts"]["genuine_forward_rules"]==0

live_store={"records":base_store["records"]+[{"source_key":"s1","ingest_type":"live_ingest","first_fetched_at":"2026-10-05T12:00:00+00:00","first_fetched_at_origin":"source_store_first_observation","admission_class":"genuine_forward","record":{"id":"s1"}}]}
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


# A forged/malformed live_ingest label without immutable first-observation provenance fails closed.
forged_store={"records":base_store["records"]+[{"source_key":"s2","ingest_type":"live_ingest","first_fetched_at":"2026-10-05T12:00:00+00:00","record":{"id":"s2"}}]}
forged_rules={"rules":base_rules["rules"]+[{"rule_id":"r2","source_id":"s2","author":"x","active":True}]}
forged=build(forged_store,forged_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert forged["integrity_pass"] is False
assert "live_ingest_missing_immutable_forward_provenance" in forged["blockers"]

# A live label before the Evidence Foundation start is not genuine forward evidence.
old_live_store={"records":base_store["records"]+[{"source_key":"s3","ingest_type":"live_ingest","first_fetched_at":"2026-10-03T23:59:59+00:00","first_fetched_at_origin":"source_store_first_observation","admission_class":"genuine_forward","record":{"id":"s3"}}]}
old_live_rules={"rules":base_rules["rules"]+[{"rule_id":"r3","source_id":"s3","author":"x","active":True}]}
old_live=build(old_live_store,old_live_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert old_live["integrity_pass"] is False
assert "live_ingest_missing_immutable_forward_provenance" in old_live["blockers"]
print("PASS Spec 1.7 genuine-forward admission lock")


# M1 hotfix: a legitimate rekeyed duplicate may inherit live_ingest from its genuine-forward parent.
# It is diagnostic only: no blocker, no live rule, no forward event.
rekey_store={"records":base_store["records"]+[{
 "source_key":"s-rekey","ingest_type":"live_ingest",
 "first_fetched_at":"2026-10-05T12:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "admission_class":"rekeyed_duplicate",
 "identity_parent_source_key":"s-parent",
 "record":{"id":"s-rekey"}
}]}
rekey_rules={"rules":base_rules["rules"]+[{"rule_id":"r-rekey","source_id":"s-rekey","author":"x","active":True}]}
rekey_families={"assignments":base_families["assignments"]+[{"rule_id":"r-rekey","definition_hash":"defhash","active":True}]}
rekey_events={"scoring_engine_version":"event_score@6.15.8l","events":base_events["events"]+[{
 "event_id":"e-rekey","rule_id":"r-rekey","point_in_time_status":"source_not_genuine_forward","scoreable":False,
 "primary_exclusion_reason":"non_point_in_time_source"
}]}
rekey_out=build(rekey_store,rekey_rules,rekey_families,rekey_events,spec,now="2026-10-06T00:00:00Z")
assert rekey_out["integrity_pass"] is True
assert "live_ingest_missing_immutable_forward_provenance" not in rekey_out["blockers"]
assert rekey_out["counts"]["rekeyed_live_inherited_sources"]==1
assert rekey_out["counts"]["genuine_forward_rules"]==0
assert rekey_out["counts"]["forward_eventscore_events"]==0
assert "s-rekey" in rekey_out["details"]["rekeyed_live_inherited_source_ids"]

# Genuine forward with invalid provenance remains a blocker.
bad_genuine_store={"records":base_store["records"]+[{
 "source_key":"s-bad-genuine","ingest_type":"live_ingest",
 "first_fetched_at":"2026-10-05T12:00:00+00:00",
 "first_fetched_at_origin":"wrong_origin",
 "admission_class":"genuine_forward",
 "record":{"id":"s-bad-genuine"}
}]}
bad_genuine_rules={"rules":base_rules["rules"]+[{"rule_id":"r-bg","source_id":"s-bad-genuine","author":"x","active":True}]}
bad_genuine=build(bad_genuine_store,bad_genuine_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert bad_genuine["integrity_pass"] is False
assert "live_ingest_missing_immutable_forward_provenance" in bad_genuine["blockers"]

# Missing admission class + live_ingest is suspicious.
missing_class_store={"records":base_store["records"]+[{
 "source_key":"s-missing","ingest_type":"live_ingest",
 "first_fetched_at":"2026-10-05T12:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "record":{"id":"s-missing"}
}]}
missing_class_rules={"rules":base_rules["rules"]+[{"rule_id":"r-missing","source_id":"s-missing","author":"x","active":True}]}
missing_class=build(missing_class_store,missing_class_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert missing_class["integrity_pass"] is False
assert "live_ingest_missing_immutable_forward_provenance" in missing_class["blockers"]

# Unknown admission class + live_ingest is suspicious.
unknown_class_store={"records":base_store["records"]+[{
 "source_key":"s-unknown","ingest_type":"live_ingest",
 "first_fetched_at":"2026-10-05T12:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "admission_class":"unexpected_class",
 "record":{"id":"s-unknown"}
}]}
unknown_class_rules={"rules":base_rules["rules"]+[{"rule_id":"r-unknown","source_id":"s-unknown","author":"x","active":True}]}
unknown_class=build(unknown_class_store,unknown_class_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert unknown_class["integrity_pass"] is False
assert "live_ingest_missing_immutable_forward_provenance" in unknown_class["blockers"]

# backfill + live_ingest is impossible under migrate_sources and must fail.
bad_backfill_store={"records":base_store["records"]+[{
 "source_key":"s-backfill-live","ingest_type":"live_ingest",
 "first_fetched_at":"2026-10-05T12:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "admission_class":"backfill",
 "record":{"id":"s-backfill-live"}
}]}
bad_backfill_rules={"rules":base_rules["rules"]+[{"rule_id":"r-backfill-live","source_id":"s-backfill-live","author":"x","active":True}]}
bad_backfill=build(bad_backfill_store,bad_backfill_rules,base_families,base_events,spec,now="2026-10-06T00:00:00Z")
assert bad_backfill["integrity_pass"] is False
assert "live_ingest_missing_immutable_forward_provenance" in bad_backfill["blockers"]
print("PASS Forward Guard rekeyed-live diagnostic / impossible live-state blockers")
