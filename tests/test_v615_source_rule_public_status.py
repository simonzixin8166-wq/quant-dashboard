import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from public_research_evidence_status import build

events={
 "spec_version":"1.7","scoring_engine_version":"event_score@6.15.8l",
 "events":[]
}
coex={"counts":{"events_total":47}}
readiness={"ready_for_v616":False,"blockers":["mature20"],"observed":{"mature_20_effective_units":0,"mature_60_effective_units":0}}
family={"counts":{"forward_rules_observed":0}}
promotion={"counts":{"passed":0,"statistical_criteria_passed":0}}
health={"status":"waiting_for_first_genuine_forward_rule","integrity_pass":True,"forward_path_observed":False,"first_scoreable_forward_observed":False,"counts":{"genuine_forward_rules":0},"blockers":[]}
funnel={
 "schema_version":"1.0","status":"baseline_established","generated_at":"2026-10-05T00:00:00Z",
 "new_sources_total":0,
 "terminal_reason_counts":{"no_operations":0},
 "terminal_reason_share":{"no_operations":None},
 "conservation":{"terminal_total":0,"expected_total":0,"pass":True},
 "downstream_counts":{"operations_total":0,"propositions_total":0,"new_forward_rules_total":0,"independent_authors":0,"cumulative_forward_rules":0,"cumulative_forward_authors":0},
 "low_confidence_genuine_forward_sources":{"new":0,"cumulative":0,"review_required":False}
}
out=build(events,coex,readiness,family,promotion,health,funnel)
assert out["source_rule_funnel"]["status"]=="baseline_established"
assert out["source_rule_funnel"]["new_sources_total"]==0
assert out["source_rule_funnel"]["non_gating"] is True
assert out["source_rule_funnel"]["result_blind"] is True
assert out["maturity_clock"]["status"]=="not_started"
assert out["maturity_clock"]["genuine_forward_rules"]==0
assert out["evidence_layers"]["legacy_observational_archive"]["count"]==47
assert out["promotion"]["production_effect"]=="none"

health2=dict(health);health2["counts"]={"genuine_forward_rules":1}
events2={"spec_version":"1.7","scoring_engine_version":"event_score@6.15.8l","events":[{
 "point_in_time_status":"eligible","scoreable":False,"baseline_timestamp_utc":"2026-10-06T13:30:00+00:00","scores":{}
}]}
out2=build(events2,coex,readiness,family,promotion,health2,funnel)
assert out2["maturity_clock"]["status"]=="started"
assert out2["maturity_clock"]["first_eligible_baseline_timestamp_utc"]=="2026-10-06T13:30:00+00:00"
print("PASS public evidence status funnel/maturity adapter")
