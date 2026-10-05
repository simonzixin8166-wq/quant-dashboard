import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("si",ROOT/"scripts"/"source_intelligence_engine.py")
si=importlib.util.module_from_spec(spec); spec.loader.exec_module(si)

sample=[
 {"id":"1","source":"wenxuecity","source_kind":"forum","author":"yifan99","published_at":"2026-09-30 12:00:00","title":"INTC sell put 复盘","url":"https://bbs.wenxuecity.com/cfzh/1.html","excerpt":"这次看错了，卖 put 后做失败复盘。"},
 {"id":"2","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-09-30 13:00:00","title":"INTC 加仓","url":"https://bbs.wenxuecity.com/cfzh/2.html","excerpt":"继续加仓，但需要注意风险。"},
]
out=si.build(sample)
assert out["counts"]["records"]==2
assert out["counts"]["failure_candidates"]>=1
assert out["counts"]["action_records"]>=1
assert any(x["symbol"]=="INTC" for x in out["thesis_candidates"])
assert out["research_alerts"]
assert all("MyAlpha" in x["myalpha_view"] or "核对" in x["myalpha_view"] for x in out["research_alerts"])
assert "Sell Put" in out["topic_groups"]
print("PASS source intelligence engine")


fulltext_sample=[
 {"id":"bl","source":"wenxuecity","source_kind":"blog","author":"BrightLine","published_at":"2026-08-18",
  "title":"子弹与耐心","url":"https://blog.wenxuecity.com/myblog/82458/202608/14095.html",
  "symbols":["NBIS","QCOM"],"themes_hint":["风险管理"],"archive_only":False,
  "operations":[
    {"symbols":["NBIS"],"entry_1":180.0,"entry_2":150.0,"exit_line":250.0,"actions":["sell"]},
    {"symbols":["QCOM"],"sell_put_strike":150.0,"actions":["sell_put","no_direct_stock_buy"]}
  ],
  "portfolio_rules":[{"type":"cash_floor","anchor_index":2},{"type":"one_tranche_at_a_time","anchor_index":3}],
  "lessons":[{"type":"cash_too_early","anchor_index":4},{"type":"process_wrong","anchor_index":5}]}
]
o2=si.build(fulltext_sample)
assert o2["counts"]["structured_operations"]==2
assert o2["counts"]["portfolio_rule_records"]==1
assert o2["counts"]["lesson_records"]==1
assert o2["operation_cases"][0]["operations"][0]["entry_1"]==180.0
assert "具体条件" in o2["research_alerts"][0]["source_view"]
assert "Sell Put K=150" in o2["research_alerts"][0]["source_view"]

assert o2["operation_cases"][0]["portfolio_rules"] == ["cash_floor","one_tranche_at_a_time"]
assert o2["operation_cases"][0]["lessons"] == ["cash_too_early","process_wrong"]
assert "组合规则：cash_floor / one_tranche_at_a_time" in o2["research_alerts"][0]["source_view"]

third=si.attribute_operation("段永平的93条语录，对不上他自己的13F",{"symbols":["NVDA"],"actions":["buy"]})
assert third["attribution"]=="third_party_example"
plan=si.attribute_operation("子弹与耐心：8·18 AI板块大跌手记。",{"symbols":["NBIS"],"entry_1":180,"entry_2":150})
assert plan["attribution"]=="author_plan"

# V5.9.1 historical reparse: explicit forum tickers + English method language
reparsed=si.build([
 {"id":"r1","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"JPM must hold above April high or larger pullback","url":"https://example/r1","excerpt":"Tech stocks need a strong close and breakout."},
 {"id":"r2","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"MM shaking both longs and shorts","url":"https://example/r2","excerpt":""},
])
rr=reparsed["records"]
assert "JPM" in rr[0]["symbols"]
assert "趋势确认" in rr[0]["topics"]
assert "MM" not in rr[1]["symbols"]
assert reparsed["parser_version"]=="5.9.1"
assert reparsed["counts"]["historically_reparsed"]==2
print("PASS V5.9.1 historical reparse")

# V5.9.1 false-positive guards
guarded=si.build([
 {"id":"g1","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"SMH also flying, 620 now!","url":"https://example/g1","excerpt":""},
 {"id":"g2","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"Yeap. But still need a strong close tomorrow though","url":"https://example/g2","excerpt":""},
 {"id":"g3","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"No, TA never looked good","url":"https://example/g3","excerpt":""},
])
gm={x["id"]:x for x in guarded["records"]}
assert gm["g1"]["symbols"]==["SMH"], gm["g1"]["symbols"]
assert "卖出/退出" not in gm["g2"]["actions"], gm["g2"]["actions"]
assert "趋势确认" in gm["g2"]["topics"]
assert "TA" not in gm["g3"]["symbols"], gm["g3"]["symbols"]
print("PASS V5.9.1 false-positive guards")

# V5.9.1 upstream-feed symbol sanitization: do not preserve collector false positives.
feed_clean=si.build([
 {"id":"f1","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"SMH also flying, 620 now!","url":"https://example/f1","excerpt":"","symbols":["NOW","SMH"]},
 {"id":"f2","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"No, TA never looked good","url":"https://example/f2","excerpt":"","symbols":["TA"]},
 {"id":"f3","source":"wenxuecity","source_kind":"forum","author":"三心三意","published_at":"2026-10-01",
  "title":"NOW breaks out","url":"https://example/f3","excerpt":"","symbols":["NOW"]},
])
fm={x["id"]:x for x in feed_clean["records"]}
assert fm["f1"]["symbols"]==["SMH"], fm["f1"]["symbols"]
assert fm["f2"]["symbols"]==[], fm["f2"]["symbols"]
assert fm["f3"]["symbols"]==["NOW"], fm["f3"]["symbols"]
print("PASS V5.9.1 upstream symbol sanitization")


# Preserve YouTube collection provenance/role through Source Intelligence normalization.
yt=si.build([{
 "id":"yt1","source":"youtube","source_kind":"video","author":"RhinoFinance / 视野环球财经",
 "published_at":"2026-10-05","title":"QQQ / TSLA update","url":"https://www.youtube.com/watch?v=abc",
 "excerpt":"","source_role":"rule_supply","transcript_status":"available",
 "content_quality":"Q3","content_provider":"stockvoice.cmoney.tw",
 "content_provider_url":"https://stockvoice.cmoney.tw/post/x",
 "content_origin":"structured_summary","timestamp_evidence":True,
 "rule_candidate_allowed":False,
 "captured_at":"2026-10-05T09:00:00Z"
}])
yr=yt["records"][0]
assert yr["source"]=="youtube"
assert yr["source_kind"]=="video"
assert yr["source_role"]=="rule_supply"
assert yr["transcript_status"]=="available"
assert yr["content_quality"]=="Q3"
assert yr["content_provider"]=="stockvoice.cmoney.tw"
assert yr["content_origin"]=="structured_summary"
assert yr["timestamp_evidence"] is True
assert yr["rule_candidate_allowed"] is False
assert yr["captured_at"]=="2026-10-05T09:00:00Z"
print("PASS YouTube source provenance preservation")


# Historical YouTube learning is exposed at top level only and must never join
# source records / Source Store forward intake.
hist={
 "version":1,"mode":"historical_observational_learning_only","non_gating":True,
 "result_blind":True,
 "records":[{"archive_id":"yt_hist_x","author":"老李玩钱","quality":"Q2","forward_evidence_eligible":False}],
 "counts":{"records":1,"q1_q2_learning_eligible":1,"q5_metadata_only":0}
}
h=si.build(sample,youtube_historical_learning=hist)
assert h["youtube_historical_learning"]["counts"]["records"]==1
assert h["youtube_historical_learning"]["non_gating"] is True
assert all(x.get("id")!="yt_hist_x" for x in h["records"])
assert h["counts"]["records"]==2
print("PASS historical YouTube learning top-level isolation")
