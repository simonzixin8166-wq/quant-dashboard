import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_family_scorecard import build

spec={
 "spec_version":"1.1",
 "definitions":{
   "rule_family_definition_hash":"h",
   "multiple_testing":{
     "minimum_time_clusters_for_testing":6,
     "bootstrap_resamples":1000,
     "bootstrap_seed":6158,
     "fdr_q":0.05
   }
 },
 "thresholds":{
   "independent_authors_min":3,
   "independent_time_clusters_min":6,
   "mature_60_effective_samples_min":20
 }
}
families={"assignments":[
 {"rule_id":"r1","family_id":"f1","definition_hash":"h","active":True,"family_key":{"primary_method":"M"}},
 {"rule_id":"r2","family_id":"f1","definition_hash":"h","active":True,"family_key":{"primary_method":"M"}},
 {"rule_id":"r3","family_id":"f1","definition_hash":"h","active":True,"family_key":{"primary_method":"M"}}
]}
events=[]
authors=["a","b","c"]
# 8 independent ISO-week blocks x 3 authors = 24 effective units, all known-positive lift.
for w in range(8):
    day=3+w*7
    for i,(rid,a) in enumerate(zip(["r1","r2","r3"],authors)):
        events.append({
          "event_id":f"e{w}-{i}","rule_id":rid,"author":a,"symbol":"ABC",
          "baseline_date":f"2026-01-{day:02d}","scoreable":True,
          "scores":{"5":None,"20":None,"60":{
             "unconditional_lift":0.02,
             "direction_adjusted_return":0.03,
             "direction_adjusted_mae":-0.04,
             "unconditional_baseline_direction_adjusted_mae":-0.05,
             "excess_vs_qqq":0.01
          }}
        })
out=build({"events":events},families,spec)
assert out["counts"]["families"]==1
card=out["cards"][0]
h=card["horizons"]["60"]
assert h["effective_n"]==24
assert h["independent_time_clusters"]>=6
assert h["test_status"]=="testable"
assert h["lift_ci95"]["lower"]>0
assert h["fdr"]["reject"] is True
assert card["status"]=="statistically_reviewable"

# Repeated observations from same author/symbol/week collapse into one effective unit.
dup=dict(events[0]);dup["event_id"]="duplicate"
out2=build({"events":events+[dup]},families,spec)
assert out2["cards"][0]["horizons"]["60"]["effective_n"]==24
print("PASS V6.15.8b family clustering / block inference / FDR")
