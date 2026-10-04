import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from entry_semantics import classify_event,classify_rule
from v615_observational_events import build

next_ev={"baseline_kind":"next_session","triggered":True,"operation":{"conditions":[]}}
m=classify_event(next_ev)
assert m["entry_type"]=="next_session"
assert m["fill_status"]=="simulated_fill"
assert m["fill_confidence"]=="high"

pull={"baseline_kind":"entry_1","triggered":False,"operation":{"conditions":["pullback to support"]}}
m2=classify_event(pull)
assert m2["entry_type"]=="pullback_limit"
assert m2["fill_status"]=="no_fill"

unknown={"baseline_kind":"entry_1","triggered":True,"operation":{"conditions":[]}}
assert classify_event(unknown)["entry_type"]=="unknown"
assert classify_rule({"fields":{"entry_1":10},"conditions":[],"actions":["buy"]})=="unknown"

events={"events":[
 {"event_id":"e1","legacy_source_id":"s1","author":"a","symbol":"ABC","published_at":"2026-01-01","baseline_date":"2026-01-02","entry_type":"next_session","fill_status":"simulated_fill","primary_exclusion_reason":"missing_rule_id"},
 {"event_id":"e2","legacy_source_id":"s2","author":"b","symbol":"XYZ","primary_exclusion_reason":"unknown_entry_semantics"}
]}
validation={"events":[
 {"event_id":"e1","operation":{"attribution":"author_action","attribution_confidence":"medium"}},
 {"event_id":"e2","operation":{"attribution":"author_action"}}
]}
out=build(events,validation)
assert out["counts"]["observations"]==1
obs=out["events"][0]
assert obs["promotion_eligible"] is False
assert obs["method_score_eligible"] is False
assert obs["planner_weight_eligible"] is False
assert obs["description_role"]=="descriptive_non_validating"

# Static isolation: consumers that can affect scores, promotion or Planner must not read the store.
for rel in [
 "scripts/autonomous_research_planner.py",
 "scripts/v615_promotion_gate.py",
 "scripts/v615_family_scorecard.py",
 "scripts/v615_rule_scorecard.py",
 "scripts/method_memory_engine.py",
]:
    text=(ROOT/rel).read_text(encoding="utf-8")
    assert "observational_events.json" not in text, rel
print("PASS V6.15.8b Entry Semantics / observational-event isolation")
