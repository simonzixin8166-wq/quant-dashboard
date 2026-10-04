import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_family_scorecard import build

def end_date(day,h):
    return (pd.Timestamp(day)+pd.tseries.offsets.BDay(h)).date().isoformat()

spec={
 "spec_version":"1.3",
 "definitions":{
   "rule_family_definition_hash":"h",
   "horizons_trading_days":[5,20,60],
   "clustering":{
     "event_effective_unit":"symbol x overlap-connected realized-horizon cluster",
     "time_cluster_definition":"overlap-connected intervals"
   },
   "multiple_testing":{
     "minimum_time_clusters_for_testing":6,
     "bootstrap_resamples":1000,
     "bootstrap_seed":6158,
     "fdr_q":0.05,
     "untestable_hypothesis_pvalue_for_fdr":1.0
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
 {"rule_id":"r3","family_id":"f1","definition_hash":"h","active":True,"family_key":{"primary_method":"M"}},
 {"rule_id":"r4","family_id":"f2","definition_hash":"h","active":True,"family_key":{"primary_method":"N"}}
]}
events=[]
authors=["a","b","c"]
symbols=["AAA","BBB","CCC"]
cluster_dates=["2026-01-05","2026-04-13","2026-07-20","2026-10-26","2027-02-01","2027-05-10","2027-08-16","2027-11-22"]
for w,day in enumerate(cluster_dates):
    for i,(rid,a,sym) in enumerate(zip(["r1","r2","r3"],authors,symbols)):
        events.append({
          "event_id":f"e{w}-{i}","rule_id":rid,"author":a,"symbol":sym,
          "baseline_date":day,"scoreable":True,
          "scores":{"5":None,"20":None,"60":{
             "horizon_end_date":end_date(day,60),
             "unconditional_lift":0.02,
             "direction_adjusted_return":0.03,
             "direction_adjusted_mae":-0.04,
             "unconditional_baseline_direction_adjusted_mae":-0.05,
             "excess_vs_qqq":0.01
          }}
        })
out=build({"events":events},families,spec)
assert out["counts"]["families"]==2
assert out["multiple_testing"]["hypotheses_declared"]==6
assert out["multiple_testing"]["hypotheses_testable"]==1
cards={x["family_id"]:x for x in out["cards"]}
h=cards["f1"]["horizons"]["60"]
assert h["effective_n"]==24
assert h["independent_time_clusters"]==8
assert h["independent_authors"]==3
assert h["cluster_definition"]=="overlap_connected_realized_horizon_intervals"
assert h["test_status"]=="testable"
assert h["lift_ci95"]["lower"]>0
assert h["fdr"]["reject"] is True
assert cards["f1"]["status"]=="statistically_reviewable"
assert cards["f2"]["horizons"]["60"]["test_status"]=="not_testable"
assert cards["f2"]["horizons"]["60"]["fdr"]["p_value"]==1.0

# Same symbol/time cluster cannot be duplicated by another author.
dup=dict(events[0]);dup["event_id"]="duplicate";dup["author"]="another-author"
out2=build({"events":events+[dup]},families,spec)
cards2={x["family_id"]:x for x in out2["cards"]}
assert cards2["f1"]["horizons"]["60"]["effective_n"]==24

# Critical canary: two 60-session windows on adjacent dates overlap heavily.
# Old fixed calendar buckets could split them at a boundary; v1.3 must not.
families3={"assignments":[
 {"rule_id":"x1","family_id":"fx","definition_hash":"h","active":True,"family_key":{"primary_method":"X"}},
 {"rule_id":"x2","family_id":"fx","definition_hash":"h","active":True,"family_key":{"primary_method":"X"}}
]}
overlap=[
 {"event_id":"x-a","rule_id":"x1","author":"a","symbol":"AAA","baseline_date":"2026-03-27","scoreable":True,
  "scores":{"5":None,"20":None,"60":{"horizon_end_date":end_date("2026-03-27",60),"unconditional_lift":0.01,"direction_adjusted_return":0.02,"direction_adjusted_mae":-0.03,"unconditional_baseline_direction_adjusted_mae":-0.04,"excess_vs_qqq":0.0}}},
 {"event_id":"x-b","rule_id":"x2","author":"b","symbol":"BBB","baseline_date":"2026-03-30","scoreable":True,
  "scores":{"5":None,"20":None,"60":{"horizon_end_date":end_date("2026-03-30",60),"unconditional_lift":0.01,"direction_adjusted_return":0.02,"direction_adjusted_mae":-0.03,"unconditional_baseline_direction_adjusted_mae":-0.04,"excess_vs_qqq":0.0}}}
]
ox=build({"events":overlap},families3,spec)
hx=ox["cards"][0]["horizons"]["60"]
assert hx["independent_time_clusters"]==1
assert hx["effective_n"]==2  # two symbols, one shared price-path cluster
print("PASS V6.15.8e overlap-connected units / full FDR family / boundary canary")
