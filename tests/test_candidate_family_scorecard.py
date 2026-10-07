import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.candidate_family_scorecard import build
from scripts.evaluation_spec import load_spec

spec=load_spec()
# Empty evidence is a valid pre-forward state.
out=build({"events":[]},spec)
assert out["spec_version"]=="1.7"
assert out["counts"]["families"]==0
assert out["counts"]["promotion_gate_compatible"]==0
assert out["promotion_effect"]=="none"
assert out["production_effect"]=="none"

# One candidate family remains research-only even when it has a scoreable event.
e={
 "event_id":"e1","family_signature":"candfam_x","spec_version":"1.7",
 "scoreable":True,"author":"A","symbol":"AAA","baseline_date":"2026-01-05",
 "scores":{
   "5":{"horizon_end_date":"2026-01-12","unconditional_lift":0.01,"direction_adjusted_return":0.02,"direction_adjusted_mae":-0.01,"unconditional_baseline_direction_adjusted_mae":-0.012,"excess_vs_qqq":0.005},
   "20":None,"60":None
 }
}
out2=build({"events":[e]},spec)
card=out2["cards"][0]
assert card["candidate_family_signature"]=="candfam_x"
assert card["promotion_gate_compatible"] is False
assert card["shadow_statistical_status"]=="sample_insufficient_research_only"
assert card["horizons"]["5"]["effective_n"]==1
assert card["horizons"]["5"]["test_status"]=="not_testable"
assert out2["counts"]["promotion_gate_compatible"]==0

print("PASS candidate family shadow scorecard / Spec 1.7 statistics / no Promotion")
