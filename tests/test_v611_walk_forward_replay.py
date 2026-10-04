import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import walk_forward_replay as wr
import system_status_center as ssc

def frame(prices,start="2025-01-02"):
    idx=pd.bdate_range(start=start,periods=len(prices))
    return pd.DataFrame({
        "open":prices,
        "high":[x*1.01 for x in prices],
        "low":[x*0.99 for x in prices],
        "close":prices,
        "volume":[1000]*len(prices),
    },index=idx)

# Build deterministic CP-01 path: ATH then tier1/tier2/tier3 drawdowns and recoveries.
base=[100+i*0.2 for i in range(80)]
path=base+[112,108,100,95,90,85,80,78,82,90,100,112,115,110,100,92,86,80,75,70]
qqqm=frame(path)
vgt=frame([100+i*0.15 for i in range(len(path))])
qld=frame([100+i*0.10 for i in range(len(path))])
qqq=frame([100+i*0.12 for i in range(len(path))])

store={"QQQM":qqqm,"VGT":vgt,"QLD":qld,"QQQ":qqq}
out=wr.build(store=store,now=datetime(2026,10,4,3,30,tzinfo=timezone.utc))
assert out["mode"]=="research_only"
assert out["evidence_provenance"]=="historical_replay_post_rule_design"
assert out["forward_evidence_mixed"] is False
assert out["automatic_promotion"] is False
assert out["production_rule_mutation"] is False
assert out["coverage"]["CP-01"]["status"]=="complete"
assert out["coverage"]["CP-02"]["status"]=="blocked"
assert "VIX" in out["coverage"]["CP-02"]["missing"]
assert out["coverage"]["CP-03"]["status"]=="blocked"
assert "SMH" in out["coverage"]["CP-03"]["missing"]
assert out["summary"]["replayable_playbooks"]==1
assert out["summary"]["blocked_playbooks"]==2
assert out["summary"]["raw_events"]>0
assert out["summary"]["effective_clusters"]<=out["summary"]["raw_events"]

# Replay records must always carry historical provenance and never Forward provenance.
for e in out["recent_replay_events"]:
    assert e["evidence_provenance"]=="historical_replay_post_rule_design"
    assert e["scoreable"] is True
    assert "forward_out_of_sample" not in json.dumps(e)

# CP-01 event state is causal from cumulative ATH; horizons are only present when mature.
events=wr.cp01_events("QQQM",qqqm,qqq)
assert events
assert all(e["playbook_id"]=="CP-01" for e in events)
assert all(e["state_detail"] in {"tier1","tier2","tier3"} for e in events)
assert all(e["rule_hash"] for e in events)
for e in events:
    for h in ("5","20","60"):
        o=e["outcomes"][h]
        if o:
            assert "return" in o and "mae" in o and "mfe" in o
            assert "excess_vs_benchmark" in o
            assert isinstance(o["aligned"],bool)

# Conservative clustering must not report more effective observations than raw.
stats=out["statistics"]
for row in stats.values():
    assert row["effective_clusters"]<=row["raw_events"]
    for h in ("5","20","60"):
        hs=row["horizons"][h]
        assert hs["effective_n"]<=hs["raw_n"]
        ci=hs["aligned_rate_ci95"]
        if hs["raw_n"]:
            assert 0<=ci["low"]<=ci["high"]<=1

# Missing core history blocks CP-01 instead of silently approximating.
blocked=wr.build(store={"QQQ":qqq,"QQQM":qqqm,"VGT":vgt},now=datetime(2026,10,4,3,30,tzinfo=timezone.utc))
assert blocked["coverage"]["CP-01"]["status"]=="blocked"
assert "QLD" in blocked["coverage"]["CP-01"]["missing"]
assert blocked["summary"]["raw_events"]==0

# Public system status must classify replay as research-only.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"replay.json"
    p.write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("walk_forward_replay",p,datetime.now(timezone.utc))
    assert h["freshness"]=="fresh"
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.11 Walk-Forward Replay (research-only)" in workflow
assert "module_failure_marker.py walk_forward_replay" in workflow
manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/walk_forward_replay.json" in manifest
ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.11 Historical Replay · Research Only" in ui
assert "historical_replay_post_rule_design" in ui
assert "缺少依赖的数据不会用近似条件补齐" in ui

print("PASS V6.11 walk-forward replay / provenance isolation / coverage blockers / effective sample counts")
