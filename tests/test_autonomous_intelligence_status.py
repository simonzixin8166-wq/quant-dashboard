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
