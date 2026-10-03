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
assert out["version"]=="7.2.0"
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

module_graph={"modules":[{"id":"tab-cn-hk","name":"A股港股","learning":"candidate"}]}
out3=s.build(evidence,method,planner,{},module_graph)
cand=next(x for x in out3["candidates"] if x["kind"]=="module_learning_design")
assert cand["scope"]=="tab-cn-hk"
assert cand["state"]=="shadow"
assert cand["promotion_eligible"] is False

execution={"results":[{"unknowns":["a","b"]} for _ in range(5)]}
out4=s.build(evidence,method,planner,{},None,execution)
gap=next(x for x in out4["candidates"] if x["kind"]=="research_process")
assert gap["scope"]=="evidence_coverage"
assert gap["proposed_change"]["require_explicit_unknowns"] is True
assert gap["state"]=="shadow"

cross_hist={"records":[{"level":"high","outcomes":{"20":{"return":-0.03}}} for _ in range(20)]}
out5=s.build(evidence,method,planner,{},None,None,cross_hist)
ca_cand=next(x for x in out5["candidates"] if x["scope"]=="cross_asset_divergence")
assert ca_cand["kind"]=="research_weight"
assert ca_cand["evidence_n"]==20
assert ca_cand["state"]=="shadow"
assert ca_cand["proposed_change"]["priority_weight_delta"]==3

breadth_hist={"records":[{"level":"fragile","outcomes":{"20":{"return":-0.02}}} for _ in range(20)]}
out6=s.build(evidence,method,planner,{},None,None,None,breadth_hist,{})
b_cand=next(x for x in out6["candidates"] if x["scope"]=="breadth_intelligence")
assert b_cand["evidence_n"]==20
assert b_cand["proposed_change"]["priority_weight_delta"]==2

regime_hist={"records":[{"level":"high","outcomes":{"20":{"return":-0.025}}} for _ in range(20)]}
out7=s.build(evidence,method,planner,{},None,None,None,{},regime_hist)
r_cand=next(x for x in out7["candidates"] if x["scope"]=="regime_combination")
assert r_cand["evidence_n"]==20
assert r_cand["proposed_change"]["priority_weight_delta"]==3
