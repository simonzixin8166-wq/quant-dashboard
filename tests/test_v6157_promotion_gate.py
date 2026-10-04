import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from v615_promotion_gate import build
spec={"spec_version":"1.0","thresholds":{"independent_authors_min":3,"independent_time_clusters_min":6,"mature_60_effective_samples_min":20,"lift_ci95_lower_bound_gt":0}}
reg={"rules":[{"rule_id":"r","source_snapshot_hash":"s","normalized_rule_hash":"n","url":"u","method_candidates":[]}]}
events={"events":[{"rule_id":"r","triggered":True,"scoreable":True,"direction":"bullish","data_quality":{"status":"ok"}}]}
good={"cards":[{"rule_id":"r","independent_authors":3,"independent_time_clusters":6,"horizons":{"60":{"mature_n":20,"lift_ci95":{"lower":0.01},"direction_adjusted_mae_mean":-0.05,"benchmark_direction_adjusted_mae_mean":-0.06}}}]}
out=build(good,{"records":[]},reg,events,spec)
assert out["results"][0]["passed"] is True
bad={"cards":[{"rule_id":"r","independent_authors":1,"independent_time_clusters":1,"horizons":{"60":{"mature_n":0,"lift_ci95":{"lower":None},"direction_adjusted_mae_mean":None,"benchmark_direction_adjusted_mae_mean":None}}}]}
out2=build(bad,{"records":[]},reg,events,spec)
assert out2["results"][0]["passed"] is False
assert out2["results"][0]["production_effect"]=="none"
# Option without real contract outcome must stay closed.
regopt={"rules":[{"rule_id":"r","source_snapshot_hash":"s","normalized_rule_hash":"n","url":"u","method_candidates":["Sell Put"]}]}
evopt={"events":[{"rule_id":"r","triggered":True,"scoreable":False,"direction":"option_structure","data_quality":{"status":"ok"}}]}
out3=build(good,{"records":[]},regopt,evopt,spec)
assert out3["results"][0]["passed"] is False
assert "option_has_real_contract_outcome" in out3["results"][0]["missing"]
print("PASS V6.15.7 promotion gate defaults closed / no production effect")
