import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_promotion_gate import build

spec={
 "spec_version":"1.1",
 "definitions":{"rule_family_definition_hash":"h"},
 "promotion_activation":{"state":"shadow_until_v6158c_controls_pass"},
 "thresholds":{
   "independent_authors_min":3,
   "independent_time_clusters_min":6,
   "mature_60_effective_samples_min":20,
   "lift_ci95_lower_bound_gt":0,
   "mae_noninferiority_ci95_lower_bound_gte":0.0,
   "max_single_symbol_effective_unit_share":0.40
 }
}
registry={"rules":[
 {"rule_id":"r1","source_snapshot_hash":"s","normalized_rule_hash":"n","url":"u"},
 {"rule_id":"r2","source_snapshot_hash":"s2","normalized_rule_hash":"n2","url":"u2"},
 {"rule_id":"r3","source_snapshot_hash":"s3","normalized_rule_hash":"n3","url":"u3"}
]}
families={"assignments":[
 {"rule_id":"r1","family_id":"f1","definition_hash":"h","active":True},
 {"rule_id":"r2","family_id":"f1","definition_hash":"h","active":True},
 {"rule_id":"r3","family_id":"f1","definition_hash":"h","active":True}
]}
events={"events":[
 {"rule_id":"r1","triggered":True,"scoreable":True,"direction":"bullish","data_quality":{"status":"ok"}},
 {"rule_id":"r2","triggered":True,"scoreable":True,"direction":"bullish","data_quality":{"status":"ok"}},
 {"rule_id":"r3","triggered":True,"scoreable":True,"direction":"bullish","data_quality":{"status":"ok"}}
]}
good={"cards":[{
 "family_id":"f1",
 "family_key":{"instrument_type":"equity","primary_method":"趋势确认"},
 "member_rule_ids":["r1","r2","r3"],
 "independent_authors":3,
 "horizons":{"60":{
   "effective_n":20,
   "independent_time_clusters":6,
   "independent_authors":3,
   "lift_ci95":{"lower":0.01},
   "fdr":{"reject":True},
   "direction_adjusted_mae_mean":-0.05,
   "benchmark_direction_adjusted_mae_mean":-0.06,
   "mae_noninferiority_ci95":{"lower":0.001,"upper":0.02},
   "single_symbol_effective_unit_share_max":0.35
 }}
}]}
out=build(good,{"records":[]},registry,families,events,spec)
row=out["results"][0]
assert row["statistical_criteria_passed"] is True
assert row["passed"] is False
assert row["state"]=="shadow_criteria_pass"
assert row["production_effect"]=="none"

# Once a future spec explicitly activates the gate, the same synthetic evidence can pass.
active={**spec,"promotion_activation":{"state":"active"}}
out2=build(good,{"records":[]},registry,families,events,active)
assert out2["results"][0]["passed"] is True

bad={"cards":[{
 "family_id":"f1","family_key":{"instrument_type":"equity"},
 "member_rule_ids":["r1"],"independent_authors":1,
 "horizons":{"60":{
   "effective_n":0,"independent_time_clusters":0,"independent_authors":1,"lift_ci95":{"lower":None},
   "fdr":None,"direction_adjusted_mae_mean":None,"benchmark_direction_adjusted_mae_mean":None,
   "mae_noninferiority_ci95":{"lower":None,"upper":None},"single_symbol_effective_unit_share_max":None
 }}
}]}
out3=build(bad,{"records":[]},registry,families,events,active)
assert out3["results"][0]["passed"] is False
print("PASS V6.15.8b family promotion gate / shadow activation / no production effect")
