import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("s",ROOT/"scripts"/"self_improvement_engine.py")
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

method={"methods":[
 {"method":"仓位与加减仓","direct_validated_events":10,"performance":{"20":{"alignment_rate":0.7}}},
 {"method":"Sell Put","direct_validated_events":9,"performance":{"20":{"alignment_rate":0.35}}},
]}
evidence={"failure_attribution":{"external_outcome_reviews":[{} for _ in range(12)]}}
planner={"version":"6.0.0","counts":{"open":7}}
out=s.build(evidence,method,planner,{})
assert out["version"]=="7.0.0"
assert out["production_brain"]["mode"]=="locked"
assert out["promotion_gate"]["automatic_production_promotion"] is False
assert len(out["candidates"])==3
assert all(x["state"]=="shadow" for x in out["candidates"])
assert any(x["proposed_change"].get("priority_weight_delta")==3 for x in out["candidates"])
assert any(x["proposed_change"].get("priority_weight_delta")==-3 for x in out["candidates"])

prev={"candidates":[]}
for c in out["candidates"]:
    cc=dict(c);cc["shadow_runs"]=4
    prev["candidates"].append(cc)
evidence2={"failure_attribution":{"external_outcome_reviews":[{} for _ in range(25)]}}
out2=s.build(evidence2,method,planner,prev)
guard=next(x for x in out2["candidates"] if x["kind"]=="process_guardrail")
assert guard["shadow_runs"]==5
assert guard["promotion_eligible"] is True
assert guard["state"]=="eligible_for_review"
print("PASS V7 self-improvement shadow engine")
