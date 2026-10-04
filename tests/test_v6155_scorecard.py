import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_rule_scorecard import build

def ev(i,scoreable=True):
 return {"event_id":f"e{i}","rule_id":"r1","author":"a","baseline_date":f"2026-01-{i+1:02d}","scoreable":scoreable,
 "scores":{"5":{"direction_adjusted_return":.01,"unconditional_lift":.001,"excess_vs_qqq":0,"direction_adjusted_mae":-.01,"unconditional_baseline_direction_adjusted_mae":-.02},
 "20":None,"60":None}}
events={"events":[ev(0),ev(1),{**ev(2),"scoreable":False}]}
attr={"events":[{"event_id":"e0","primary_method":"M"},{"event_id":"e1","primary_method":"M"},{"event_id":"e2","primary_method":"M"}]}
reg={"rules":[{"rule_id":"r1","author":"a","title":"t"}]}
spec={"spec_version":"1.0","thresholds":{"mature_60_effective_samples_min":20}}
out=build(events,attr,reg,spec)
c=out["cards"][0]
assert c["analysis_count"]==3 and c["evidence_count"]==2
assert "hit_rate" not in c["horizons"]["5"]
assert c["status"]=="sample_insufficient_research_only"
print("PASS V6.15.5 scorecard evidence/analysis separation")
