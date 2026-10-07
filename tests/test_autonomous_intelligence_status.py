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


out=build()
wake=out["automatic_resume_contract"]
assert wake["parameter_definition_queue_rebuilt_each_source_cycle"] is True
assert wake["forward_observer_runs_each_source_cycle"] is True
assert wake["source_validation_schedule_present"] is True
assert wake["manual_open_required"] is False
assert wake["d_unlock_rule"]["requires_forward_20d_outcomes"] is True
assert wake["d_unlock_rule"]["requires_candidate_evidence_family_pass"] is True
assert wake["d_unlock_rule"]["current_candidate_evidence_families_passed"]>=0
assert wake["d_unlock_rule"]["unlocked"] is False
print("PASS automatic wait-state resume / D unlock contract")


out=build()
cm=out["milestones"]["C_validation_evidence"]["metrics"]
assert "candidate_signal_direction_governance_complete" in cm
assert "candidate_evidence_promotion_state" in cm
if cm["candidate_signal_direction_governance_complete"]:
    assert "explicit_candidate_signal_direction_governance" not in out["milestones"]["C_validation_evidence"]["remaining"]
print("PASS Candidate direction governance and evidence-promotion status")
