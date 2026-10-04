import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import autonomous_research_planner as arp
import autonomous_research_executor as are

method={
 "methods":[
  {
   "method":"仓位与加减仓","direct_validated_events":6,"context_validated_events":0,
   "status":"direct_developing",
   "evidence_maturity":{"state":"direct_developing","basis_horizon":20,"mature_n":5,"alignment_rate":None},
   "performance":{
      "5":{"n":6,"alignment_rate":0.75,"avg_return":0.02,"avg_excess_vs_qqq":0.01},
      "20":{"n":5,"alignment_rate":0.6667,"avg_return":0.03,"avg_excess_vs_qqq":0.02},
      "60":{"n":0,"alignment_rate":None},
   },
   "failure_examples":[{"symbol":"TSLA","horizon":20,"return":-0.1,"alignment":"not_aligned"}],
  },
  {
   "method":"趋势确认","direct_validated_events":10,"context_validated_events":2,
   "status":"outcome_challenging",
   "evidence_maturity":{"state":"outcome_challenging","basis_horizon":20,"mature_n":10,"alignment_rate":0.3},
   "performance":{"20":{"n":10,"alignment_rate":0.3,"avg_return":-0.01,"avg_excess_vs_qqq":-0.02}},
   "failure_examples":[],
  },
  {
   "method":"风险管理","direct_validated_events":0,"context_validated_events":12,
   "status":"context_only",
   "evidence_maturity":{"state":"context_only","basis_horizon":None,"mature_n":0,"alignment_rate":None},
   "performance":None,
  },
 ]
}

planner=arp.build(
  agent={},learning={},evidence={},method=method,source={},previous={},
  modules={},cross_asset={},breadth_intelligence={},regime_memory={},data={},controlled_policy={}
)

mv=[x for x in planner["queue"] if x["kind"]=="method_validation"]
assert {x["key"] for x in mv}=={"仓位与加减仓","趋势确认"}
by={x["key"]:x for x in mv}
assert by["仓位与加减仓"]["method_evidence_state"]=="direct_developing"
assert by["仓位与加减仓"]["priority"]==70
assert by["趋势确认"]["method_evidence_state"]=="outcome_challenging"
assert by["趋势确认"]["priority"]==82
assert "不自动改变方法权重" in by["趋势确认"]["why_now"]

# Context-only high-volume source evidence remains a gap task, not a direct-validation claim.
gap=next(x for x in planner["queue"] if x["kind"]=="method_evidence_gap" and x["key"]=="风险管理")
assert gap["priority"]==62
assert not any(x["kind"]=="method_validation" and x["key"]=="风险管理" for x in planner["queue"])

# Executor interprets method evidence and actively preserves counter-evidence/unknowns.
support,counter,unknowns=are.method_validation_brief(by["仓位与加减仓"],method)
assert any("direct_developing" in x for x in support)
assert any("20日直接样本 5" in x for x in support)
assert any("反例" in x for x in counter)
assert any("证据仍在积累期" in x for x in unknowns)

support2,counter2,unknowns2=are.method_validation_brief(by["趋势确认"],method)
assert any("outcome_challenging" in x for x in support2)
assert any("偏挑战" in x for x in counter2)

# Full task execution remains research-only.
result=are.execute_task(by["趋势确认"],{
 "method":method,"learning":{},"evidence":{},"source":{},"data":{},"official":{},"events":{},
 "modules":{},"event_windows":{},"cross_asset":{},"cross_asset_history":{},
 "breadth_intelligence":{},"breadth_history":{},"regime_memory":{},"regime_history":{},
})
assert result["kind"]=="method_validation"
assert result["research_status"]=="analyzed"
assert "不能自动下单" in result["guardrail"]

ui=(ROOT/"docs/assets/autonomous-agent.js").read_text(encoding="utf-8")
assert "method_validation:'方法证据'" in ui

print("PASS V6.13.3 method evidence state -> autonomous research follow-up / no trading mutation")
