import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.autonomous_intelligence_status import build

out=build()
assert out["formal_app_version"]=="6.9.0"
assert out["development_policy"]["bug_fix_behavior"].startswith("fix + regression")
assert out["development_policy"]["today_cockpit_is_sole_action_outlet"] is True
assert out["development_policy"]["automatic_trading"] is False
assert set(out["milestones"])=={
 "A_source_reliability","B_autonomous_learning_core","C_validation_evidence",
 "D_decision_fusion_watchlist","E_single_action_outlet"
}
print("PASS autonomous intelligence master status")

out=build()
c=out["milestones"]["C_validation_evidence"]
assert c["engineering_chain_complete"] is True
assert c["zero_forward_is_valid"] is True
assert c["state"]=="engineering_closed_forward_evidence_accumulating"
assert c["evidence_state"] in {"awaiting_first_genuine_forward_candidate","forward_evidence_accumulating"}
print("PASS Milestone C engineering-closed / evidence-accumulating state")

out=build()
a=out["milestones"]["A_source_reliability"]
assert a["metrics"]["primary_subject_attribution_active"] is True
assert a["state"]=="operational_continuous_audit"
assert "primary_subject_attribution" not in a["remaining"]
print("PASS Milestone A Primary Subject Attribution completion state")

out=build()
cm=out["milestones"]["C_validation_evidence"]["metrics"]
assert "historical_replay_raw_event_instances" in cm
assert "historical_replay_unique_state_entries" in cm
assert "historical_replay_duplicate_event_instances" in cm
assert "historical_replay_overlap_rate" in cm
assert "historical_replay_events" not in cm
print("PASS honest historical replay overlap metrics in master status")

out=build()
b=out["milestones"]["B_autonomous_learning_core"]
assert b["metrics"]["generic_moving_average_support_complete"] is True
assert b["metrics"]["generic_moving_average_windows"]==[20,50,200]
assert "increase generic candidate coverage" not in b["remaining"]
assert b["engineering_chain_complete"] is True
assert b["state"]=="engineering_closed_waiting_for_source_definitions"
assert b["evidence_dependency_state"] in {"waiting_for_source_definitions","all_parameterized_conditions_resolved"}
assert b["metrics"]["parameter_definition_queue_items"]>=0
if b["metrics"]["parameter_definition_queue_items"]>0:
    assert b["remaining"]==["await explicit source-defined indicator parameters"]
else:
    assert b["remaining"]==[]
print("PASS Milestone B engineering-closed / source-definition-wait state")
