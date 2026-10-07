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
