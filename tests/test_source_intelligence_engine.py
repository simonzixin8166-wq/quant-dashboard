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
