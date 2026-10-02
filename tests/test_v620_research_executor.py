import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rx",ROOT/"scripts"/"autonomous_research_executor.py")
rx=importlib.util.module_from_spec(spec);spec.loader.exec_module(rx)

planner={
 "version":"6.1.0",
 "today":[
  {"task_id":"t1","kind":"market_anomaly","key":"LITE","title":"LITE研究","priority":88,
   "questions":["驱动是什么？"],"evidence_sources":["market_data"]},
  {"task_id":"t2","kind":"method_evidence_gap","key":"Sell Put","title":"Sell Put补证据","priority":62,
   "questions":["哪些可直接归因？"],"evidence_sources":["method_memory"]},
 ],
 "queue":[]
}
learning={"situation_memory":[
 {"symbol":"LITE","stage":"二次启动","research_priority":82,
  "historical_stage_evidence":{"n60":12,"median60":0.08},
  "contradictions":[{"message":"周线尚未确认"}]}
]}
evidence={"failure_attribution":{"external_outcome_reviews":[
 {"symbol":"LITE","event_id":"e1","review_tags":["trend_false_positive"]}
]}}
method={"methods":[
 {"method":"Sell Put","direct_validated_events":1,"context_validated_events":19,"performance":None,"failure_examples":[]}
]}
source={"records":[{"symbols":["LITE"],"published_at":"2026-10-01","title":"LITE"}]}
modules={"modules":[]}
official={"symbols":{"LITE":{"status":"ok","filings":[{"form":"8-K","filing_date":"2026-10-01","excerpts":["Item 8.01 official event"]}]}}}
events={"symbols":{"LITE":{"status":"ok","news":[{"title":"Lumentum update","publisher":"Reuters","source_type":"newswire","source_priority":1}],"peer_context":{"peer_count":3,"direction":"broad_positive","avg_day_change":0.025}}}}
data={"trend_pulse":{"LITE":{"state":"二次启动","data_integrity":{"status":"CHECK","label":"有限校验"}}}}
artifacts={"learning":learning,"evidence":evidence,"method":method,"source":source,"modules":modules,"official":official,"events":events,"data":data}
out=rx.build(planner,artifacts,{})
assert out["version"]=="6.4.0"
assert out["summary"]["analyzed"]==2
lite=next(x for x in out["results"] if x["key"]=="LITE")
assert lite["supporting_evidence"]
assert lite["counter_evidence"]
assert lite["unknowns"]
assert lite["research_status"]=="analyzed"
sp=next(x for x in out["results"] if x["key"]=="Sell Put")
assert any("Context 19" in x for x in sp["supporting_evidence"])
assert any("18" in x for x in sp["counter_evidence"])
assert out["policy"]["automatic_orders"] is False

out2=rx.build(planner,artifacts,out)
lite2=next(x for x in out2["results"] if x["key"]=="LITE")
assert lite2["analysis_runs"]==2
assert lite2["first_analyzed_at"]==lite["first_analyzed_at"]
print("PASS V6.2 autonomous research executor")

assert any("SEC官方披露" in x for x in lite["supporting_evidence"])
assert not any("尚未完成本任务对应的最新SEC官方披露核验" in x for x in lite["unknowns"])

# ETFs should not be treated as missing single-company SEC evidence.
planner_etf={"version":"6.1.0","today":[{"task_id":"te","kind":"market_anomaly","key":"VGT","title":"VGT研究","priority":72,"questions":[],"evidence_sources":[]}],"queue":[]}
artifacts_etf={**artifacts,"learning":{"situation_memory":[{"symbol":"VGT","stage":"高位钝化","research_priority":60,"historical_stage_evidence":{},"contradictions":[]}]},"source":{"records":[]},"official":{"symbols":{}},"data":{"trend_pulse":{"VGT":{"state":"高位钝化","data_integrity":{"status":"OK"}}}}}
etf=rx.build(planner_etf,artifacts_etf,{})["results"][0]
assert any("ETF/基金工具" in x for x in etf["supporting_evidence"])
assert not any("SEC官方披露核验" in x for x in etf["unknowns"])

# Failure reviews should consume available SEC timeline evidence.
planner_fail={"version":"6.1.0","today":[{"task_id":"tf","kind":"failure_review","key":"LITE","title":"LITE失败","priority":68,"questions":[],"evidence_sources":[]}],"queue":[]}
fail=rx.build(planner_fail,artifacts,{})["results"][0]
assert any("SEC官方时间线" in x for x in fail["supporting_evidence"])

assert any("高优先级事件源" in x for x in lite["supporting_evidence"])
assert any("同业联动" in x for x in lite["supporting_evidence"])
