import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("p",ROOT/"scripts"/"autonomous_research_planner.py")
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

agent={
 "watchlist_attention":[
  {"symbol":"LITE","level":"action","research_priority":88,"reasons":["单日大涨"],"run_count":1},
  {"symbol":"QQQ","level":"quiet","research_priority":40,"reasons":[]}
 ],
 "discovery_queue":[{"symbol":"XYZ","event_strength":"high","next_step":"核对官方事件"}]
}
evidence={"failure_attribution":{"external_outcome_reviews":[
 {"event_id":"e1","symbol":"IREN","title":"failure"},
 {"event_id":"e2","symbol":"IREN","title":"failure2"},
]}}
method={"methods":[{"method":"趋势确认","direct_validated_events":1,"context_validated_events":10}]}
out=p.build(agent,{},evidence,method,{}, {})
assert out["version"]=="6.1.0"
assert out["counts"]["open"]>=4
assert any(x["kind"]=="market_anomaly" and x["key"]=="LITE" for x in out["queue"])
assert any(x["kind"]=="failure_review" for x in out["queue"])
assert any(x["kind"]=="method_evidence_gap" for x in out["queue"])
assert any(x["kind"]=="discovery" and x["key"]=="XYZ" for x in out["queue"])
assert "automatic_order" in out["planner_policy"]["forbidden"]

prev={"queue":[out["queue"][0]]}
out2=p.build(agent,{},evidence,method,{},prev)
same=next(x for x in out2["queue"] if x["task_id"]==out["queue"][0]["task_id"])
assert same["run_count"]==2
print("PASS V6 autonomous research planner")

failure=next(x for x in out["queue"] if x["kind"]=="failure_review")
assert failure["key"]=="IREN"
assert failure["sample_count"]==2
assert failure["priority"]==68
live=next(x for x in out["queue"] if x["kind"]=="market_anomaly")
assert live["priority"]>=88
assert out["today"][0]["kind"]=="market_anomaly"

modules={"audit":{"coverage_ok":False},"modules":[{"id":"tab-engine","name":"核心策略信号","learning":"shadow_only"}]}
out3=p.build(agent,{},evidence,method,{}, {},modules)
assert any(x["kind"]=="architecture_gap" for x in out3["queue"])
assert any(x["kind"]=="module_learning_review" and x["key"]=="tab-engine" for x in out3["queue"])
