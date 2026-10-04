import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import direction_adjusted_return,unconditional_lift
from research_boundary_guard import snapshot,check_changed_paths

assert direction_adjusted_return("bearish",-0.10)==0.10
assert direction_adjusted_return("bullish",0.10)==0.10
assert abs(unconditional_lift("bullish",0.10,0.10))<1e-12
assert check_changed_paths(["config/x.json"])==["config/x.json"]
assert check_changed_paths(["research/state/x.json"])==[]
spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
assert spec["spec_version"]=="1.0"
assert spec["thresholds"]["provisional"] is True
assert spec["change_policy"]["forbid_tuning_to_pass_named_methods"] is True
print("PASS V6.15.0 evaluation spec and boundary guard")
