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

print("PASS V6.14.3 structured source rule -> autonomous validation queue / no premature performance")
