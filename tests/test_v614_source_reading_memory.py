import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import source_reading_memory as srm
import system_status_center as ssc

source={
 "version":2,
 "records":[
  {
   "id":"r1","source":"wenxuecity","source_kind":"forum","author":"A","published_at":"2026-10-01",
   "title":"我准备分两档买入 QQQ","url":"u1","symbols":["QQQ"],"topics":["仓位与加减仓"],
   "excerpt":"如果站上MA20再考虑第二档；跌破退出线就离场。",
   "operations":[{
      "symbols":["QQQ"],"actions":["planned_buy"],"entry_1":700,"entry_2":680,"exit_line":650,
      "conditions":["站上 MA20 再考虑第二档"],"attribution":"author_plan"
   }],
   "portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r2","source":"wenxuecity","source_kind":"forum","author":"B","published_at":"2026-10-01",
   "title":"谈 Sell Put","url":"u2","symbols":["NVDA"],"topics":["Sell Put"],
   "excerpt":"我觉得NVDA长期不错。",
   "operations":[],
   "portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r3","source":"wenxuecity","source_kind":"forum","author":"C","published_at":"2026-10-01",
   "title":"第三方例子","url":"u3","symbols":["TSLA"],"topics":["仓位与加减仓"],
   "excerpt":"",
   "operations":[{
      "symbols":["TSLA"],"actions":["buy"],"entry_1":300,"attribution":"third_party_example"
   }],
   "portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r4","source":"wenxuecity","source_kind":"forum","author":"D","published_at":"2026-10-01",
   "title":"趋势修复","url":"u4","symbols":["AMD"],"topics":["趋势确认"],
   "excerpt":"如果突破MA50，可能进入趋势修复。",
   "operations":[],"portfolio_rules":[],"lessons":[]
  }
 ]
}

out=srm.build(source)
assert out["version"]=="6.14.0"
assert out["mode"]=="research_only_free_first"
assert out["counts"]["source_records"]==4
assert out["counts"]["records_with_testable_rules"]==1
assert out["counts"]["testable_rules"]==1

r1=next(x for x in out["records"] if x["source_id"]=="r1")
kinds=[x["kind"] for x in r1["propositions"]]
assert "fact" in kinds
assert "trigger" in kinds
assert "invalidation" in kinds
assert "testable_rule" in kinds
rule=next(x for x in r1["propositions"] if x["kind"]=="testable_rule")
assert rule["testable"] is True
assert rule["evidence"]["attribution"]=="author_plan"
assert rule["evidence"]["rule"]["fields"]["entry_1"]==700
assert rule["evidence"]["rule"]["fields"]["exit_line"]==650

# Topic alone never creates a direct/testable rule.
r2=next(x for x in out["records"] if x["source_id"]=="r2")
assert r2["testable_rule_count"]==0
assert not any(x["kind"]=="testable_rule" for x in r2["propositions"])

# A third-party structured example may be preserved as facts but cannot become
# an author-owned testable rule.
r3=next(x for x in out["records"] if x["source_id"]=="r3")
assert any(x["kind"]=="fact" for x in r3["propositions"])
assert r3["testable_rule_count"]==0

# Prose technical condition can remain a contextual trigger, but it is not
# silently promoted to a testable rule.
r4=next(x for x in out["records"] if x["source_id"]=="r4")
tr=next(x for x in r4["propositions"] if x["kind"]=="trigger")
assert tr["testable"] is False
assert r4["testable_rule_count"]==0

# Public artifact contains no production mutation path.
blob=json.dumps(out,ensure_ascii=False).lower()
for forbidden in ("automatic_order","position_size_change","production_threshold_change"):
    assert forbidden not in blob

# Status Center classification remains research-only.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"source_reading_memory.json"
    p.write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("source_reading_memory",p,datetime.now(timezone.utc))
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.14 Source Reading Memory" in workflow
assert workflow.index("Build Source Intelligence Learning") < workflow.index("Build V6.14 Source Reading Memory")
assert workflow.index("Build V6.14 Source Reading Memory") < workflow.index("Validate External Source Outcomes")
assert "module_failure_marker.py source_reading_memory" in workflow

manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/source_reading_memory.json" in manifest

print("PASS V6.14 source reading propositions / author ownership / no topic promotion / research-only")
