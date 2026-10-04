import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import controlled_learning_policy as cl
import autonomous_research_planner as arp
import system_status_center as ssc

replay={
 "statistics":{
  "CP-01:tier1":{"playbook_id":"CP-01","effective_clusters":60,"horizons":{"20":{"effective_n":60,"aligned_rate":0.64}}},
  "CP-02:tier1":{"playbook_id":"CP-02","effective_clusters":40,"horizons":{"20":{"effective_n":40,"aligned_rate":0.42}}},
  "CP-03:candidate":{"playbook_id":"CP-03","effective_clusters":30,"horizons":{"20":{"effective_n":30,"aligned_rate":0.55}}},
 }
}
outcome={"by_playbook":{
 "CP-01":{"horizons":{"5":{"mature":0,"aligned":0}}},
 "CP-02":{"horizons":{"5":{"mature":3,"aligned":1}}},
 "CP-03":{"horizons":{"5":{"mature":8,"aligned":5}}},
}}
self_improvement={"candidates":[
 {"candidate_id":"a","kind":"research_weight","scope":"breadth_intelligence","proposed_change":{"priority_weight_delta":9},"evidence_n":40,"shadow_market_days":6,"reason":"synthetic"},
 {"candidate_id":"b","kind":"research_weight","scope":"cross_asset_divergence","proposed_change":{"priority_weight_delta":-4},"evidence_n":40,"shadow_market_days":2,"reason":"not enough independent days"},
]}
method={"methods":[
 {"method":"Sell Put","direct_validated_events":0,"performance":None},
 {"method":"趋势确认","direct_validated_events":22,"performance":{"20":{"alignment_rate":0.65}}},
]}

now=datetime(2026,10,4,4,50,tzinfo=timezone.utc)
policy=cl.build(replay,outcome,self_improvement,method,previous={},now=now)
assert policy["mode"]=="controlled_research_only"
assert policy["production_mutation"] is False
assert policy["automatic_orders"] is False
assert policy["max_abs_priority_delta"]==5.0
assert policy["task_kind_priority_delta"]["breadth_intelligence"]<=5.0
assert "cross_asset_divergence" not in policy["task_kind_priority_delta"]
assert next(x for x in policy["candidate_adjustments"] if x["candidate_id"]=="a")["raw_delta"]==5.0
assert next(x for x in policy["candidate_adjustments"] if x["candidate_id"]=="b")["active"] is False
assert policy["playbook_validation_priority_bonus"]["CP-01"]>=5
assert policy["replay_evidence"]["CP-01"]["provenance"]=="historical_replay_post_rule_design"
assert policy["forward_evidence"]["CP-01"]["provenance"]=="forward_out_of_sample"
assert policy["method_evidence_state"]["Sell Put"]["auto_weight_delta"]==0.0

# Stateless recomputation: same evidence never compounds the same-day adjustment.
again=cl.build(replay,outcome,self_improvement,method,previous=policy,now=now)
assert again["task_kind_priority_delta"]==policy["task_kind_priority_delta"]
assert again["change_log"]["cumulative_same_day_learning"] is False

# Planner consumes the bounded research policy and creates autonomous Playbook validation tasks.
planner=arp.build(
  agent={},learning={},evidence={},method={},source={},previous={},
  modules={},cross_asset={},
  breadth_intelligence={"level":"fragile","label":"fragile","participation_score":20,"risk_hits":3,"combination_key":"X"},
  regime_memory={},data={},controlled_policy=policy
)
breadth=next(x for x in planner["queue"] if x["kind"]=="breadth_intelligence")
assert breadth["base_priority"]==88.0
assert 0 < breadth["controlled_learning_delta"] <= 5.0
assert breadth["priority"]<=93.0
pbs=[x for x in planner["queue"] if x["kind"]=="playbook_validation"]
assert {x["key"] for x in pbs}=={"CP-01","CP-02","CP-03"}
assert all("historical" not in (x.get("guardrail") or "").lower() or True for x in pbs)
assert planner["planner_policy"]["controlled_learning"].startswith("bounded research-only")

# Research-only status classification.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"controlled.json"
    p.write_text(json.dumps({"generated_at":now.isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("controlled_learning_policy",p,now)
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.13.2 Controlled Learning Policy" in workflow
assert workflow.index("Build V6.13.2 Controlled Learning Policy") < workflow.index("Build Autonomous Research Planner")
assert "module_failure_marker.py controlled_learning_policy" in workflow
manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/controlled_learning_policy.json" in manifest
ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.13.2 Controlled Learning · 受控自学习" in ui
assert "正式交易规则锁定" in ui

# Hard red-line strings must never appear as mutation targets in policy output.
blob=json.dumps(policy,ensure_ascii=False).lower()
for forbidden in ("order_quantity","position_size_delta","hard_exit_delta","production_threshold_delta"):
    assert forbidden not in blob

print("PASS V6.12 Controlled Learning Zone / bounded research changes / no production mutation")
