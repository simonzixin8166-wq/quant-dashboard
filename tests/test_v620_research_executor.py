import importlib.util
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
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
assert out["version"]=="6.9.0"
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
for required_key in ['"event_windows"','"events"','"cross_asset"','"cross_asset_history"','"breadth_intelligence"','"breadth_history"','"regime_memory"','"regime_history"','"data"']:
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
assert any("10年期" in x for x in row["supporting_evidence"])
assert any("NFCI" in x for x in row["counter_evidence"])
assert any("MOVE" in x for x in row["unknowns"])

planner_bi={"version":"6.8.2","today":[{"task_id":"bi1","kind":"breadth_intelligence","key":"US_BREADTH","title":"宽度研究","priority":88,"questions":[],"evidence_sources":[]}],"queue":[]}
art_bi={**artifacts,
 "breadth_intelligence":{"level":"fragile","participation_score":31.5,"combination_key":"B20_LOW|SPY_RSP_GAP",
  "signals":[{"label":"SPY领先RSP","hit":True,"severity":"high","reason":"20日领先6%"}],
  "unknowns":["QQQE待补齐"]},
 "breadth_history":{"records":[]}}
birow=rx.build(planner_bi,art_bi,{})["results"][0]
assert birow["kind"]=="breadth_intelligence"
assert any("SPY领先RSP" in x for x in birow["supporting_evidence"])
assert any("QQQE" in x for x in birow["unknowns"])

planner_rg={"version":"6.8.2","today":[{"task_id":"rg1","kind":"regime_combination","key":"US_REGIME","title":"组合环境","priority":92,"questions":[],"evidence_sources":[]}],"queue":[]}
art_rg={**artifacts,
 "regime_memory":{"level":"high","state_id":"CROSS_HIGH|BREADTH_FRAGILE|VIX_LOW",
  "cross_asset":{"label":"高位跨资产背离","risk_hits":4},
  "breadth":{"label":"参与度脆弱","participation_score":31.5},
  "vix":{"value":16.5,"zone":"low"}},
 "regime_history":{"records":[]}}
rgrow=rx.build(planner_rg,art_rg,{})["results"][0]
assert rgrow["kind"]=="regime_combination"
assert any("组合状态" in x for x in rgrow["supporting_evidence"])
assert any("同时出现" in x for x in rgrow["supporting_evidence"])
assert any("VIX=" in x and "尚未确认" in x for x in rgrow["counter_evidence"])

planner_lr={"version":"6.8.2","today":[{"task_id":"lr1","kind":"leverage_rebound","key":"QQQ","title":"TQQQ vs QQQ LEAPS","priority":84,"questions":[],"evidence_sources":[]}],"queue":[]}
art_lr={**artifacts,"data":{"leverage_rebound":{"status":"candidate","label":"10%+回调后修复确认","drawdown252":-0.12,
 "supporting_evidence":["QQQ已重新站上上行MA20"],"counter_evidence":["市场宽度仍脆弱"],"unknowns":["具体IV待核验"],
 "source_method":{"author":"lionhill / 狮山巡礼","title":"市场大调整时：TQQQ还是QQQ LEAPS"}}}}
lrrow=rx.build(planner_lr,art_lr,{})["results"][0]
assert lrrow["kind"]=="leverage_rebound"
assert any("MA20" in x for x in lrrow["supporting_evidence"])
assert any("宽度" in x for x in lrrow["counter_evidence"])
assert any("IV" in x for x in lrrow["unknowns"])
assert any("Source Hypothesis" in x for x in lrrow["supporting_evidence"])

assert any("中位收益 8.0%" in x for x in lite["supporting_evidence"])
assert any("平均日变动 2.5%" in x for x in lite["supporting_evidence"])
