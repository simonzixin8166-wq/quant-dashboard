import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import source_rule_lifecycle as srl
import system_status_center as ssc

reading={
 "version":"6.14.2",
 "records":[{
   "source_id":"src1","author":"A","published_at":"2026-08-18","title":"multi op","url":"u",
   "propositions":[
     {"proposition_id":"p0","kind":"testable_rule","evidence":{
       "operation_index":0,"method_candidates":["仓位与加减仓"],
       "rule":{"fields":{"entry_1":100},"conditions":[],"actions":["planned_buy"]}
     }},
     {"proposition_id":"p1","kind":"testable_rule","evidence":{
       "operation_index":1,"method_candidates":["Sell Put","仓位与加减仓"],
       "rule":{"fields":{"entry_2":140,"sell_put_strike":150},"conditions":["accept_assignment_then_reassess"],"actions":["sell_put","planned_buy"]}
     }},
     {"proposition_id":"p2","kind":"testable_rule","evidence":{
       "operation_index":2,"method_candidates":["仓位与加减仓"],
       "rule":{"fields":{"entry_1":80},"conditions":[],"actions":["planned_buy"]}
     }},
   ]
 }]
}

outcomes={
 "version":"5.9.2",
 "events":[
  {
   "event_id":"src1:0:QQQ:0","symbol":"QQQ","triggered":True,"status":"developing",
   "baseline_kind":"entry_1","planned_level":100,
   "actions":["planned_buy"],"level_checks":{"entry_1":{"level":100,"touch20":{"touched":True}}},
   "alignment":{"5":"aligned","20":"aligned","60":None},
   "outcomes":{"5":{"return":0.01},"20":{"return":0.03},"60":None},
  },
  {
   "event_id":"src1:1:QCOM:0","symbol":"QCOM","triggered":False,"status":"not_triggered",
   "baseline_kind":"entry_2","planned_level":140,
   "actions":["sell_put","planned_buy"],
   "level_checks":{
     "entry_2":{"level":140,"touch20":{"touched":False},"touch60":{"touched":False}},
     "sell_put_strike":{"level":150,"touch20":{"touched":True,"date":"2026-09-01"},"touch60":{"touched":True,"date":"2026-09-01"}},
   },
   "alignment":{"5":None,"20":None,"60":None},
   "outcomes":{"5":None,"20":None,"60":None},
  },
 ]
}

out=srl.build(reading,outcomes)
assert out["version"]=="6.14.5"
assert out["mode"]=="research_only_rule_lifecycle"
assert out["counts"]["rules"]==3

by={x["rule_id"]:x for x in out["rules"]}

# Exact operation-index mapping: p0 only sees op0.
assert by["p0"]["mapped_event_ids"]==["src1:0:QQQ:0"]
assert by["p0"]["state"]=="mature_20"
assert by["p0"]["maturity"]=={"5":1,"20":1,"60":0}
assert by["p0"]["scoreable_as_method_performance"] is True

# Sell Put stays unscored even when underlying touches strike.
assert by["p1"]["mapped_event_ids"]==["src1:1:QCOM:0"]
assert by["p1"]["state"]=="option_outcome_unscored"
assert by["p1"]["underlying_strike_touched"] is True
assert by["p1"]["scoreable_as_method_performance"] is False
assert "option premium at entry" in by["p1"]["required_evidence"]
assert by["p1"]["maturity"]=={"5":0,"20":0,"60":0}

# Missing exact op mapping is explicit, never borrowed from same article.
assert by["p2"]["mapped_event_ids"]==[]
assert by["p2"]["state"]=="mapping_missing"
assert by["p2"]["scoreable_as_method_performance"] is False

assert out["counts"]["option_unscored"]==1
assert out["counts"]["mapping_missing"]==1
assert out["by_method"]["Sell Put"]["option_outcome_unscored"]==1

# Public lifecycle has no trading mutation path.
blob=json.dumps(out,ensure_ascii=False).lower()
for forbidden in ("automatic_order","production_threshold_change","position_size_change"):
    assert forbidden not in blob

from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"source_rule_lifecycle.json"
    p.write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("source_rule_lifecycle",p,datetime.now(timezone.utc))
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.14.5 Structured Source Rule Lifecycle" in workflow
assert workflow.index("Validate External Source Outcomes") < workflow.index("Build V6.14.5 Structured Source Rule Lifecycle")
assert workflow.index("Build V6.14.5 Structured Source Rule Lifecycle") < workflow.index("Build Evidence Attribution Learning")
assert "module_failure_marker.py source_rule_lifecycle" in workflow

manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/source_rule_lifecycle.json" in manifest

print("PASS V6.14.5 exact operation mapping / stock maturity / Sell Put option-P&L boundary")
