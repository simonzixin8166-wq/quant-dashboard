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
event_windows={"rows":[{"symbol":"LITE","nearest_sec":{"distance_band":"near"},"nearest_event":{"distance_band":"week"}}]}
events={"symbols":{"LITE":{"status":"ok","news":[{"title":"Lumentum update","publisher":"Reuters","source_type":"newswire","source_priority":1}],"peer_context":{"peer_count":3,"direction":"broad_positive","avg_day_change":0.025}}}}
data={"trend_pulse":{"LITE":{"state":"二次启动","data_integrity":{"status":"CHECK","label":"有限校验"}}}}
artifacts={"learning":learning,"evidence":evidence,"method":method,"source":source,"modules":modules,"official":official,"event_windows":event_windows,"events":events,"data":data}
out=rx.build(planner,artifacts,{})
assert out["version"]=="6.8.0"
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

events_generic={"symbols":{"LITE":{"status":"ok","news":[{"title":"Lumentum context","publisher":"Media","source_type":"media","source_priority":2}],"peer_context":{"peer_count":1,"direction":"mixed","avg_day_change":0.01}}}}
artifacts_generic={**artifacts,"events":events_generic}
generic=rx.build({"version":"6.1.0","today":[planner["today"][0]],"queue":[]},artifacts_generic,{})["results"][0]
assert not any("已读取 1 条最近媒体事件线索" in x for x in generic["supporting_evidence"])
assert any("一般媒体线索" in x for x in generic["unknowns"])
assert any("未形成一致共振" in x for x in generic["unknowns"])

failure_artifacts={**artifacts}
planner2={"version":"6.1.0","today":[{"task_id":"f1","kind":"failure_review","key":"LITE","title":"LITE失败复盘","priority":68,"questions":[],"evidence_sources":[]}],"queue":[]}
out3=rx.build(planner2,failure_artifacts,{})
fr=out3["results"][0]
assert any("事件窗口已自动对齐" in x for x in fr["supporting_evidence"])
assert any("不代表事件造成失败" in x for x in fr["counter_evidence"])

src=(ROOT/"scripts"/"autonomous_research_executor.py").read_text(encoding="utf-8")
for required_key in ['"event_windows"','"events"','"cross_asset"','"cross_asset_history"','"breadth"','"breadth_history"','"data"']:
    assert required_key in src

planner_ca={"version":"6.7.0","today":[{"task_id":"ca1","kind":"cross_asset_divergence","key":"US_MARKET","title":"美股跨资产背离","priority":86,"questions":[],"evidence_sources":[]}],"queue":[]}
art_ca={**artifacts,
 "cross_asset":{"level":"high","label":"高位跨资产背离","risk_hits":4,"high_hits":3,
  "signals":[
   {"label":"10年期美债收益率压力","hit":True,"severity":"high","reason":"10Y上行"},
   {"label":"金融条件仍有缓冲","hit":True,"severity":"offset","reason":"NFCI仍宽松"}],
  "thesis":["价格趋势仍强，但折现率压力上升。"],"unknowns":["MOVE待接入"]},
 "cross_asset_history":{"records":[]}}
out_ca=rx.build(planner_ca,art_ca,{})
row=out_ca["results"][0]
assert row["kind"]=="cross_asset_divergence"
assert any("10年期" in x for x in row["counter_evidence"])
assert any("NFCI" in x for x in row["supporting_evidence"])
assert any("MOVE" in x for x in row["unknowns"])


planner_br={"version":"6.8.0","today":[{"task_id":"br1","kind":"breadth_divergence","key":"US_PARTICIPATION","title":"参与度背离","priority":84,"questions":[],"evidence_sources":[]}],"queue":[]}
art_br={**artifacts,
 "breadth":{"level":"high","label":"高位参与度收缩","fingerprint":"EQUITY_NEAR_HIGH+BREADTH_WEAK+AD_NEGATIVE+EQUAL_WEIGHT_WEAK",
  "flags":{"EQUITY_NEAR_HIGH":True,"BREADTH_WEAK":True,"AD_NEGATIVE":True,"NEW_HIGHS_THIN":True,"EQUAL_WEIGHT_WEAK":True,"VIX_LOW":True},
  "breadth":{"ad_line_20d":-2.2,"new_high_52w_pct":0.06},
  "equal_weight":{"rsp_spy":{"available":True,"pair":"RSP/SPY","chg20":-0.02,"signal":"weak"},"qqqe_qqq":{"available":True,"pair":"QQQE/QQQ","chg20":-0.03,"signal":"weak"}},
  "current_combination_history":{"5":{"n":0},"20":{"n":0},"60":{"n":0}},"unknowns":[]},
 "breadth_history":{"records":[]}}
br=rx.build(planner_br,art_br,{})["results"][0]
assert br["kind"]=="breadth_divergence"
assert any("RSP/SPY" in x for x in br["counter_evidence"])
assert any("A/D" in x for x in br["counter_evidence"])
assert any("成熟样本不足" in x for x in br["unknowns"])
