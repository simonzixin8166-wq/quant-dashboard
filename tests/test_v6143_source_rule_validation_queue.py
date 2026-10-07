import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import autonomous_research_planner as arp
import autonomous_research_executor as are

method={
 "methods":[
  {
   "method":"Sell Put","direct_validated_events":0,"context_validated_events":4,
   "status":"context_only","evidence_maturity":{"state":"context_only","mature_n":0},
   "source_reading":{"testable_rule_candidates":1,"state":"candidate_rules_available"},
   "performance":None,
  },
  {
   "method":"仓位与加减仓","direct_validated_events":6,"context_validated_events":0,
   "status":"direct_developing","evidence_maturity":{"state":"direct_developing","mature_n":5},
   "source_reading":{"testable_rule_candidates":10,"state":"candidate_rules_available"},
   "performance":{"20":{"n":5,"alignment_rate":0.67}},
  },
  {
   "method":"风险管理","direct_validated_events":0,"context_validated_events":6,
   "status":"context_only","evidence_maturity":{"state":"context_only","mature_n":0},
   "source_reading":{"testable_rule_candidates":0,"state":"no_structured_rule_candidate"},
   "performance":None,
  },
 ]
}

planner=arp.build(
 agent={},learning={},evidence={},method=method,source={},previous={},
 modules={},cross_asset={},breadth_intelligence={},regime_memory={},data={},controlled_policy={}
)
assert planner["version"]=="6.14.3"

candidates=[x for x in planner["queue"] if x["kind"]=="method_rule_candidate"]
assert len(candidates)==1
task=candidates[0]
assert task["key"]=="Sell Put"
assert task["priority"]==68
assert task["testable_rule_candidates"]==1
assert task["direct_validated_events"]==0
assert "不能直接视为方法有效" in task["why_now"]
assert "source_reading_memory" in task["evidence_sources"]

# Existing direct evidence follows the ordinary method-validation loop instead
# of creating a duplicate candidate task.
assert not any(x["kind"]=="method_rule_candidate" and x["key"]=="仓位与加减仓" for x in planner["queue"])
assert any(x["kind"]=="method_validation" and x["key"]=="仓位与加减仓" for x in planner["queue"])

# Context-only method without an explicit structured candidate is not promoted.
assert not any(x["kind"]=="method_rule_candidate" and x["key"]=="风险管理" for x in planner["queue"])

reading={
 "version":"6.14.2",
 "records":[
  {
   "source_id":"r1","author":"BrightLine","title":"NVDA Sell Put 计划",
   "topics":["Sell Put","风险管理"],
   "propositions":[
    {
     "kind":"testable_rule",
     "text":"NVDA：结构化操作规则",
     "evidence":{
       "attribution":"author_plan",
       "method_candidates":["Sell Put"],
       "rule":{"actions":["sell_put"],"fields":{"sell_put_strike":150},"conditions":["price above support"]},
     },
    },
    # Topic/view context must not be treated as a structured candidate.
    {"kind":"author_view","text":"风险管理很重要","evidence":{}},
   ],
  },
  {
   "source_id":"r2","author":"Other","title":"只谈 Sell Put",
   "topics":["Sell Put"],
   "propositions":[{"kind":"author_view","text":"我喜欢 Sell Put","evidence":{}}],
  },
 ]
}

support,counter,unknowns=are.method_rule_candidate_brief(task,reading,method)
assert any("结构规则候选 1 条" in x for x in support)
assert any("BrightLine" in x for x in support)
assert any("sell_put" in x.lower() or "sell put" in x.lower() for x in support)
assert any("sell_put_strike=150" in x for x in support)
assert any("Direct=0" in x for x in unknowns)
assert any("文章主题" in x and "不能替代" in x for x in counter)
assert not any("Other" in x for x in support)

artifacts={
 "source_reading":reading,"method":method,
 "learning":{},"evidence":{},"source":{},"modules":{},"official":{},
 "event_windows":{},"events":{},"cross_asset":{},"cross_asset_history":{},
 "breadth_intelligence":{},"breadth_history":{},"regime_memory":{},"regime_history":{},"data":{},
}
result=are.execute_task(task,artifacts)
assert result["kind"]=="method_rule_candidate"
assert result["research_status"]=="analyzed"
assert result["unknowns"]
assert result["counter_evidence"]
assert "不能自动下单" in result["guardrail"]

ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "method_rule_candidate:'结构规则验证'" in ui

# Prose-derived candidates use a weaker, separate queue. Machine-ready
# conditions go to validation preparation; undefined source indicators go to
# definition research first. Neither path is a Rule Registry/Promotion input.
prose_reading={
 "version":"6.14.7",
 "records":[
  {
   "source_id":"p1","author":"AuthorA","title":"AMD MA50 确认","symbols":["AMD"],
   "propositions":[{
     "proposition_id":"pc1","kind":"candidate_rule","text":"AMD候选",
     "evidence":{"candidate_rule":{
       "symbols":["AMD"],
       "conditions":[{"condition_id":"price_above_ma50","machine_ready":True}],
       "state_hint":"CONFIRMATION","machine_readiness":"machine_ready",
       "needs_definition":[],"raw_evidence":["价格站上MA50"],"source_derived_only":True
     }}
   }]
  },
  {
   "source_id":"p2","author":"yifan99","title":"AMZN趋势形成","symbols":["AMZN"],
   "propositions":[{
     "proposition_id":"pc2","kind":"candidate_rule","text":"AMZN候选",
     "evidence":{"candidate_rule":{
       "symbols":["AMZN"],
       "conditions":[
         {"condition_id":"tcds_cross_zero","machine_ready":False},
         {"condition_id":"ppo_above_signal","machine_ready":False},
         {"condition_id":"price_above_ma50","machine_ready":True}
       ],
       "state_hint":"EARLY_ENTRY","machine_readiness":"partial_needs_definition",
       "needs_definition":["tcds_cross_zero","ppo_above_signal"],
       "raw_evidence":["TCDS由负值回升并转正","PPO上穿Signal","价格站上MA50"],
       "source_derived_only":True
     }}
   }]
  },
  {
   "source_id":"p3","author":"yifan99","title":"AMZN趋势形成（论坛镜像）","symbols":["AMZN"],
   "propositions":[{
     "proposition_id":"pc3","kind":"candidate_rule","text":"AMZN候选镜像",
     "evidence":{"candidate_rule":{
       "symbols":["AMZN"],
       "conditions":[
         {"condition_id":"price_above_ma50","machine_ready":True},
         {"condition_id":"ppo_above_signal","machine_ready":False},
         {"condition_id":"tcds_cross_zero","machine_ready":False}
       ],
       "state_hint":"EARLY_ENTRY","machine_readiness":"partial_needs_definition",
       "needs_definition":["tcds_cross_zero","ppo_above_signal"],
       "raw_evidence":["同一方法重复发布"],
       "source_derived_only":True
     }}
   }],
  {
   "source_id":"p4","author":"yifan99","title":"TCDS参数说明","symbols":["AMZN"],
   "propositions":[{
     "proposition_id":"clue1","kind":"author_view",
     "text":"TCDS 参数与计算周期定义需要结合原公式核对。","evidence":{}
   }]
  }
 ]
}
planner2=arp.build(
 agent={},learning={},evidence={},method={"methods":[]},source={},previous={},
 modules={},cross_asset={},breadth_intelligence={},regime_memory={},data={},controlled_policy={},
 source_reading=prose_reading
)
pval=next(x for x in planner2["queue"] if x["kind"]=="prose_candidate_validation")
pdef=next(x for x in planner2["queue"] if x["kind"]=="prose_candidate_definition")
assert sum(1 for x in planner2["queue"] if x["kind"]=="prose_candidate_definition")==1
assert pdef["source_count"]==2
assert len(pdef["provenance"])==2
assert pval["symbol"]=="AMD" and pval["machine_readiness"]=="machine_ready"
assert pdef["symbol"]=="AMZN"
assert set(pdef["needs_definition"])=={"tcds_cross_zero","ppo_above_signal"}
assert "不允许猜测" in pdef["why_now"]

support,counter,unknowns=are.prose_candidate_brief(pdef,prose_reading)
assert any("yifan99" in x and "AMZN" in x for x in support)
assert any("2 条来源记录" in x and "去重" in x for x in support)
assert any("来源状态语义：EARLY_ENTRY" in x for x in support)
assert any("tcds_cross_zero" in x and "猜测" in x for x in counter)
assert any("ppo_above_signal" in x for x in unknowns)
assert any("tcds_cross_zero" in x and "自动回查" in x for x in support)
assert any("TCDS参数说明" in x for x in support)
assert any("疑似定义线索" in x for x in unknowns)
assert any("Rule Registry" in x and "Promotion" in x for x in counter)

prose_artifacts=dict(artifacts)
prose_artifacts["source_reading"]=prose_reading
res=are.execute_task(pdef,prose_artifacts)
assert res["kind"]=="prose_candidate_definition"
assert res["research_status"]=="analyzed"
assert res["counter_evidence"] and res["unknowns"]

# The research selector reserves a slot for learning candidates without
# converting them into an action or order.
selected=are.select_tasks({"today":[],"queue":[pdef,pval]},limit=1)
assert len(selected)==1
assert selected[0]["kind"] in {"prose_candidate_definition","prose_candidate_validation"}

ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "prose_candidate_definition:'候选方法定义'" in ui
assert "prose_candidate_validation:'候选规则验证'" in ui

print("PASS V6.14.3 structured + prose candidate -> autonomous research queue / no premature promotion")
