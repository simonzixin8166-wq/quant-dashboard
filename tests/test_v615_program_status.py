import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ps",ROOT/"scripts"/"research_program_status.py")
ps=importlib.util.module_from_spec(spec);spec.loader.exec_module(ps)
out=ps.build()
assert "phases" in out
for k in [
 "A_historical_learning_bridge","B_author_intelligence","C_forward_intake",
 "D_rule_candidate_pipeline","E_eventscore_forward_tracking","F_author_scorecard",
 "G_rule_family","H_contradiction_memory","I_promotion_gate",
 "J_source_intelligence_ui","K_autonomous_learning_loop","L_v615_acceptance",
]:
    assert k in out["phases"], k
assert out["phases"]["A_historical_learning_bridge"]["pass"] is True
assert out["phases"]["C_forward_intake"]["pass"] is True
assert out["phases"]["I_promotion_gate"]["pass"] is True
assert "20/60" in out["phases"]["L_v615_acceptance"]["detail"]
assert "do not advance" in out["next_transition"]
print("PASS V6.15 end-to-end program status")
