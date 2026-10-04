import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import forward_learning_feedback as flf
import controlled_learning_policy as cl
import system_status_center as ssc

outcome={
 "by_playbook":{
  "CP-01":{
   "trigger_records":4,"baseline_mismatch":0,"history_or_definition_missing":0,"timing_uncertain":0,
   "horizons":{
    "5":{"mature":4,"aligned":3,"not_aligned":1,"pending":0},
    "20":{"mature":4,"aligned":3,"not_aligned":1,"pending":0},
    "60":{"mature":0,"aligned":0,"not_aligned":0,"pending":4},
   },
   "by_state_detail":{"tier1":{"trigger_records":4,"horizons":{"20":{"mature":4,"aligned":3,"not_aligned":1,"pending":0}}}},
  },
  "CP-02":{
   "trigger_records":5,"baseline_mismatch":0,"history_or_definition_missing":0,"timing_uncertain":0,
   "horizons":{
    "5":{"mature":5,"aligned":2,"not_aligned":3,"pending":0},
    "20":{"mature":5,"aligned":1,"not_aligned":4,"pending":0},
    "60":{"mature":0,"aligned":0,"not_aligned":0,"pending":5},
   },
   "by_state_detail":{"tier1":{"trigger_records":3,"horizons":{"20":{"mature":3,"aligned":0,"not_aligned":3,"pending":0}}}},
  },
  "CP-03":{
   "trigger_records":3,"baseline_mismatch":1,"history_or_definition_missing":0,"timing_uncertain":1,
   "horizons":{
    "5":{"mature":2,"aligned":1,"not_aligned":1,"pending":1},
    "20":{"mature":0,"aligned":0,"not_aligned":0,"pending":3},
    "60":{"mature":0,"aligned":0,"not_aligned":0,"pending":3},
   },
   "by_state_detail":{},
  },
 }
}
replay={
 "statistics":{
  "CP-01:tier1":{"playbook_id":"CP-01","state_detail":"tier1","horizons":{"20":{"effective_n":60,"aligned_rate":0.64}}},
  "CP-02:tier1":{"playbook_id":"CP-02","state_detail":"tier1","horizons":{"20":{"effective_n":80,"aligned_rate":0.62}}},
  "CP-03:candidate":{"playbook_id":"CP-03","state_detail":"candidate","horizons":{"20":{"effective_n":50,"aligned_rate":0.60}}},
 }
}
now=datetime(2026,10,4,5,40,tzinfo=timezone.utc)
feedback=flf.build(outcome,replay,previous={},now=now)

assert feedback["mode"]=="shadow_research_only"
assert feedback["change_log"]["automatic_promotion"] is False
assert feedback["playbooks"]["CP-01"]["state"]=="forward_supportive"
assert feedback["playbooks"]["CP-02"]["state"]=="forward_challenging"
assert feedback["playbooks"]["CP-03"]["state"]=="data_quality_review"
assert feedback["playbooks"]["CP-02"]["forward_provenance"]=="forward_out_of_sample"
assert feedback["playbooks"]["CP-02"]["replay_provenance"]=="historical_replay_post_rule_design"
assert any(x["tag"]=="forward_direction_challenging" for x in feedback["playbooks"]["CP-02"]["attribution"])
assert any(x["tag"]=="replay_forward_divergence" for x in feedback["playbooks"]["CP-02"]["attribution"])
assert any(x["tag"]=="baseline_integrity" for x in feedback["playbooks"]["CP-03"]["attribution"])
assert any(x["tag"]=="late_detection_timing" for x in feedback["playbooks"]["CP-03"]["attribution"])
assert [x["playbook_id"] for x in feedback["challengers"]]==["CP-02"]
chall=feedback["challengers"][0]
assert chall["state"]=="shadow_candidate"
assert chall["human_review_required"] is True
assert "automatic promotion" in [x.lower() for x in chall["forbidden_actions"]]

# Public feedback must be aggregate-only.
blob=json.dumps(feedback,ensure_ascii=False).lower()
for forbidden in ("record_id","prev_hash","record_hash","account_id","position_id"):
    assert forbidden not in blob

# Controlled Learning may use feedback to raise validation/review priority only.
policy=cl.build(
 replay=replay,
 outcome=outcome,
 self_improvement={"candidates":[]},
 method={"methods":[]},
 feedback=feedback,
 previous={},
 now=now,
)
assert policy["version"]=="6.12.1"
assert policy["production_mutation"] is False
assert policy["automatic_orders"] is False
assert policy["forward_learning_feedback"]["automatic_promotion"] is False
assert policy["forward_learning_feedback"]["playbook_states"]["CP-02"]=="forward_challenging"
assert policy["playbook_validation_priority_bonus"]["CP-02"]>=policy["playbook_validation_priority_bonus"]["CP-01"]

# Data-quality review cannot create a challenger by itself.
assert not any(x["playbook_id"]=="CP-03" for x in feedback["challengers"])

# System-status classification must remain research-only.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"feedback.json"
    p.write_text(json.dumps({"generated_at":now.isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("forward_learning_feedback",p,now)
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.12.1 Forward Learning Feedback + Challenger Shadow" in workflow
assert workflow.index("Build V6.12.1 Forward Learning Feedback + Challenger Shadow") < workflow.index("Build V6.12 Controlled Learning Policy")
assert "module_failure_marker.py forward_learning_feedback" in workflow
manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/forward_learning_feedback.json" in manifest
ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.12.1 Controlled Learning · 受控自学习" in ui
assert "Challenger 仅做影子诊断" in ui
assert "research/forward_learning_feedback.json" in ui

print("PASS V6.12.1 Forward feedback / failure attribution / Challenger shadow / no production mutation")
