import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_family_scorecard import build

spec={
 "spec_version":"1.2",
 "definitions":{
   "rule_family_definition_hash":"h",
   "horizons_trading_days":[5,20,60],
   "clustering":{"horizon_block_weeks":{"5":1,"20":4,"60":12}},
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
block_dates=["2026-01-05","2026-03-30","2026-06-22","2026-09-14","2026-12-07","2027-03-01","2027-05-24","2027-08-16"]
for w,day in enumerate(block_dates):
    for i,(rid,a,sym) in enumerate(zip(["r1","r2","r3"],authors,symbols)):
        events.append({
          "event_id":f"e{w}-{i}","rule_id":rid,"author":a,"symbol":sym,
          "baseline_date":day,"scoreable":True,
          "scores":{"5":None,"20":None,"60":{
             "unconditional_lift":0.02,
             "direction_adjusted_return":0.03,
             "direction_adjusted_mae":-0.04,
             "unconditional_baseline_direction_adjusted_mae":-0.05,
             "excess_vs_qqq":0.01
          }}
        })
out=build({"events":events},families,spec)
assert out["counts"]["families"]==2
assert out["multiple_testing"]["hypotheses_declared"]==6  # 2 frozen families x 3 horizons
assert out["multiple_testing"]["hypotheses_testable"]==1
cards={x["family_id"]:x for x in out["cards"]}
h=cards["f1"]["horizons"]["60"]
assert h["effective_n"]==24  # 3 symbols x 8 non-overlapping 60d blocks
assert h["independent_time_clusters"]==8
assert h["independent_authors"]==3
assert h["test_status"]=="testable"
assert h["lift_ci95"]["lower"]>0
assert h["fdr"]["reject"] is True
assert cards["f1"]["status"]=="statistically_reviewable"
assert cards["f2"]["horizons"]["60"]["test_status"]=="not_testable"
assert cards["f2"]["horizons"]["60"]["fdr"]["p_value"]==1.0

# Two authors on the same symbol/block do not create two effective samples.
dup=dict(events[0]);dup["event_id"]="duplicate";dup["author"]="another-author"
out2=build({"events":events+[dup]},families,spec)
cards2={x["family_id"]:x for x in out2["cards"]}
assert cards2["f1"]["horizons"]["60"]["effective_n"]==24
print("PASS V6.15.8d symbol-block units / non-overlap blocks / fixed FDR family")
