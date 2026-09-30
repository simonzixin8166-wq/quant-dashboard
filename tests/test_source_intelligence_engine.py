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
