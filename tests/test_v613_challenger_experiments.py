import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import challenger_experiment_runner as cer
import system_status_center as ssc

now=datetime(2026,10,4,6,0,tzinfo=timezone.utc)
replay={
 "version":"6.11.1",
 "statistics":{
  "CP-02:hard_exit":{"playbook_id":"CP-02","state_detail":"hard_exit","raw_events":100,"effective_clusters":70,"horizons":{"20":{"raw_n":100,"effective_n":70,"aligned_rate":0.48,"avg_return":-0.01,"avg_mae":-0.08,"avg_mfe":0.06}}},
  "CP-02:tier1":{"playbook_id":"CP-02","state_detail":"tier1","raw_events":60,"effective_clusters":50,"horizons":{"20":{"raw_n":60,"effective_n":50,"aligned_rate":0.30,"avg_return":0.02,"avg_mae":-0.04,"avg_mfe":0.05}}},
 }
}

# Replay alone must never create a challenger or experiment.
none=cer.build(
 {"version":"6.12.1","challengers":[]},
 replay,
 previous={},
 now=now,
)
assert none["status"]=="waiting_for_real_forward_challenger"
assert none["candidate_count"]==0
assert none["experiment_count"]==0
assert none["experiments"]==[]

feedback={
 "version":"6.12.1",
 "challengers":[{
   "challenger_id":"abc123",
   "playbook_id":"CP-02",
   "state":"shadow_candidate",
   "human_review_required":True,
   "reason_tags":["forward_direction_challenging"],
 }]
}
out=cer.build(feedback,replay,previous={},now=now)
assert out["status"]=="shadow_experiments_preregistered"
assert out["candidate_count"]==1
assert out["experiment_count"]==2
assert all(x["playbook_id"]=="CP-02" for x in out["experiments"])
assert all(x["state"]=="preregistered_shadow" for x in out["experiments"])
assert all(x["frozen_spec"] is True for x in out["experiments"])
assert all(x["changes_production_rule"] is False for x in out["experiments"])
assert all(x["automatic_promotion"] is False for x in out["experiments"])
assert all(x["human_review_required"] is True for x in out["experiments"])
assert all(x["baseline_snapshot"]["provenance"]=="historical_replay_post_rule_design" for x in out["experiments"])
assert all(x["execution"]["ready"] is True for x in out["experiments"])
assert all(x["execution"]["result"] is None for x in out["experiments"])
assert all(x["execution"]["result_status"]=="not_run" for x in out["experiments"])
assert len({x["experiment_id"] for x in out["experiments"]})==2

# IDs/specs are deterministic: repeated workflow runs cannot manufacture new variants.
out2=cer.build(feedback,replay,previous=out,now=now)
assert [x["experiment_id"] for x in out2["experiments"]]==[x["experiment_id"] for x in out["experiments"]]
assert [x["variant"] for x in out2["experiments"]]==[x["variant"] for x in out["experiments"]]

# Unknown or non-forward-gated playbooks produce no arbitrary experiment.
unknown=cer.build(
 {"version":"6.12.1","challengers":[{"challenger_id":"z","playbook_id":"CP-X","state":"shadow_candidate","human_review_required":True}]},
 replay,previous={},now=now)
assert unknown["candidate_count"]==1
assert unknown["experiment_count"]==0

# Public artifact must not contain raw private ledger/account identifiers.
blob=json.dumps(out,ensure_ascii=False).lower()
for forbidden in ("record_id","prev_hash","record_hash","account_id","position_id"):
    assert forbidden not in blob

# Status center must mark Challenger experiments research-only.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"challenger.json"
    p.write_text(json.dumps({"generated_at":now.isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("challenger_experiments",p,now)
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.13 Challenger Experiment Runner (preregistered shadow)" in workflow
assert workflow.index("Build V6.12.1 Forward Learning Feedback + Challenger Shadow") < workflow.index("Build V6.13 Challenger Experiment Runner")
assert workflow.index("Build V6.13 Challenger Experiment Runner") < workflow.index("Build V6.13.2 Controlled Learning Policy")
assert "module_failure_marker.py challenger_experiments" in workflow

manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/challenger_experiments.json" in manifest
ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.13 Challenger Experiments" in ui
assert "不从 Replay 单独制造候选" in ui
assert "任何晋级仍需人工复核" in ui

print("PASS V6.13 Challenger preregistration / Forward gate / frozen spec / no auto promotion")
