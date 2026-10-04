import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_component_manifest import build

registry=json.loads((ROOT/"research/specs/component_registry.json").read_text())
spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
out=build(registry,spec)
assert out["counts"]["components"]>=10
assert out["counts"]["missing_code_hashes"]==0
names={x["name"] for x in out["components"]}
assert {"event_score","rule_family","family_scorecard","statistical_controls","v616_readiness_gate"}<=names
assert out["evaluation_spec_version"]=="1.1"
print("PASS V6.15.8c component code/artifact manifest")
