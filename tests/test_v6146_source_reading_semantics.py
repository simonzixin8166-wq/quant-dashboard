import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import source_reading_memory as srm

source={
 "version":2,
 "records":[
  {
   "id":"semantic-1","source":"wenxuecity","source_kind":"forum","author":"A",
   "published_at":"2026-10-04","title":"hold until FOMO starts and then hedge :)",
   "url":"u1","symbols":["QQQ"],"topics":["市场判断"],
   "excerpt":"if FOMO never come, then sell if market breakdown",
   "operations":[],"portfolio_rules":[],"lessons":[]
  },
  {
   "id":"semantic-2","source":"blog","source_kind":"blog","author":"B",
   "published_at":"2026-10-04","title":"I think the setup may improve",
   "url":"u2","symbols":["NVDA"],"topics":["观点"],
   "excerpt":"watch liquidity and leadership",
   "operations":[],"portfolio_rules":[],"lessons":[]
  },
  {
   "id":"semantic-3","source":"blog","source_kind":"blog","author":"C",
   "published_at":"2026-10-04","title":"如果站上MA50再观察",
   "url":"u3","symbols":["AMD"],"topics":["趋势确认"],
   "excerpt":"普通背景说明",
   "operations":[],"portfolio_rules":[],"lessons":[]
  },
  {
   "id":"semantic-4","source":"blog","source_kind":"blog","author":"D",
   "published_at":"2026-10-04","title":"计划分档",
   "url":"u4","symbols":["QQQ"],"topics":["仓位与加减仓"],
   "excerpt":"我认为风险仍高",
   "operations":[{
      "symbols":["QQQ"],"actions":["planned_buy"],"entry_1":700,"exit_line":650,
      "conditions":["站上 MA20 再考虑"],"attribution":"author_plan"
   }],
   "portfolio_rules":[],"lessons":[]
  }
 ]
}

out=srm.build(source)
assert out["version"]=="6.14.6"
by={x["source_id"]:x for x in out["records"]}

# Explicit exit language is an invalidation, not a generic residual view.
r1=by["semantic-1"]
assert any(p["kind"]=="invalidation" and "sell if market breakdown" in p["text"].lower() for p in r1["propositions"])
assert all(p["kind"]!="testable_rule" for p in r1["propositions"])
assert any(p["kind"]=="non_testable_view" and "hold until fomo" in p["text"].lower() for p in r1["propositions"])

# Opinion language remains author_view; residual prose is preserved.
r2=by["semantic-2"]
assert any(p["kind"]=="author_view" for p in r2["propositions"])
assert any(p["kind"]=="non_testable_view" for p in r2["propositions"])

# Technical conditional prose stays a contextual trigger only.
r3=by["semantic-3"]
trigger=next(p for p in r3["propositions"] if p["kind"]=="trigger")
assert trigger["testable"] is False
assert trigger["evidence"]["classification"]=="explicit_trigger_language"
assert any(p["kind"]=="non_testable_view" for p in r3["propositions"])

# Structured author plan still creates the high-confidence testable rule.
r4=by["semantic-4"]
kinds={p["kind"] for p in r4["propositions"]}
for expected in ("fact","author_view","trigger","invalidation","testable_rule","non_testable_view"):
    # non_testable_view may be absent from this one record, but must exist globally.
    if expected!="non_testable_view":
        assert expected in kinds
assert r4["testable_rule_count"]==1

global_kinds=out["counts"]["by_kind"]
for expected in ("fact","author_view","trigger","invalidation","testable_rule","non_testable_view"):
    assert global_kinds.get(expected,0)>0

# No prose-only sentence is silently promoted to a testable rule.
for sid in ("semantic-1","semantic-2","semantic-3"):
    assert by[sid]["testable_rule_count"]==0

blob=json.dumps(out,ensure_ascii=False).lower()
for forbidden in ("automatic_order","production_threshold_change","position_size_change"):
    assert forbidden not in blob

ui=(ROOT/"docs"/"assets"/"knowledge.js").read_text(encoding="utf-8")
for label in ("Fact","Author View","Trigger","Invalidation","Testable Rule","Non-testable View"):
    assert label in ui

print("PASS V6.14.6 six-way Source Reading semantics / no prose promotion / research-only boundary")
