import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import playbook_outcome_engine as oe
import private_ledger as pl
import system_status_center as ssc

CFG=json.loads((ROOT/"config"/"playbook_outcomes.json").read_text(encoding="utf-8"))
DEFS=CFG["definitions"]

def frame(start="2026-10-02", days=90, start_price=100.0, step=1.0):
    idx=pd.bdate_range(start=start,periods=days)
    close=[start_price+i*step for i in range(days)]
    return pd.DataFrame({
        "open":close,
        "high":[x*1.01 for x in close],
        "low":[x*0.99 for x in close],
        "close":close,
        "volume":[1000]*days,
    },index=idx)

def event(pid,symbol,detail,baseline=100.0,date="2026-10-02"):
    return {
        "record_type":"trigger_state_event",
        "record_id":f"{pid}-{symbol}-{detail}",
        "playbook_id":pid,
        "symbol":symbol,
        "state":"TRIGGERED",
        "state_detail":detail,
        "event_date":date,
        "market_date":date,
        "baseline_close":baseline,
        "scoreable":True,
        "evidence_provenance":"forward_out_of_sample",
    }

# CP-01: bullish ETF trigger.
up=frame(step=1.0)
store={"QQQM":up,"QQQ":up.copy()}
r=oe.score_event(event("CP-01","QQQM","tier1"),DEFS["CP-01"],store,[5,20,60],0.03)
assert r["baseline_check"]=="pass"
assert all(r["outcomes"][str(h)]["aligned"] is True for h in (5,20,60))
assert r["outcomes"]["20"]["mae"] is not None and r["outcomes"]["20"]["mfe"] is not None

# CP-02 risk reduction is evaluated on QQQ and expects bearish follow-through.
down=frame(step=-0.6)
r=oe.score_event(event("CP-02","TQQQ","tier1"),DEFS["CP-02"],{"QQQ":down},[5,20,60],0.03)
assert r["evaluation_asset"]=="QQQ"
assert r["objective_group"]=="risk_reduction"
assert r["expected_direction"]=="bearish"
assert r["outcomes"]["5"]["aligned"] is True

# CP-02 restore is kept separate and expects bullish follow-through.
r=oe.score_event(event("CP-02","TQQQ","full_restore"),DEFS["CP-02"],{"QQQ":up},[5,20,60],0.03)
assert r["objective_group"]=="risk_restore"
assert r["expected_direction"]=="bullish"
assert r["outcomes"]["20"]["aligned"] is True

# CP-03 never invents LEAPS P&L: only underlying directional proxy exists.
r=oe.score_event(event("CP-03","QQQ","candidate"),DEFS["CP-03"],{"QQQ":up},[5,20,60],0.03)
assert DEFS["CP-03"]["success_basis"]=="underlying_directional_proxy"
assert r["outcomes"]["5"]["aligned"] is True
assert "option_pnl" not in r["outcomes"]["5"]

# Baseline revalidation quarantines material adjusted-history mismatch.
r=oe.score_event(event("CP-01","QQQM","tier1",baseline=80.0),DEFS["CP-01"],store,[5,20,60],0.03)
assert r["baseline_check"]=="baseline_mismatch"
assert r["outcomes"]=={}

# Incomplete horizons remain pending, never fabricated.
short=frame(days=8,step=1.0)
r=oe.score_event(event("CP-01","QQQM","tier1"),DEFS["CP-01"],{"QQQM":short,"QQQ":short},[5,20,60],0.03)
assert r["outcomes"]["5"] is not None
assert r["outcomes"]["20"] is None and r["outcomes"]["60"] is None

# Private reader may read a verified trigger chain; build publishes aggregates only and never writes.
class ReadOnlyWriter:
    def __init__(self, files):
        self.files=files
        self.write_calls=0
    def read_text(self,path):
        return self.files.get(path,""), None
    def write_text(self,*args,**kwargs):
        self.write_calls+=1
        raise AssertionError("Outcome Foundation must not write private ledger")

raw=event("CP-01","QQQM","tier1")
raw.update({"schema_version":"1.0","recorded_at":"2026-10-02T22:00:00+00:00","rule_hash":"x","rule_version":"1.0.0"})
row=pl.make_record(raw,pl.ZERO_HASH)
writer=ReadOnlyWriter({"ledger/trigger/2026-10.jsonl":pl.canonical_json(row)+"\n"})
result=oe.build(writer=writer,store=store,market_date="2026-10-02",now=datetime(2026,10,4,3,0,tzinfo=timezone.utc))
assert result["mode"]=="shadow_no_forward_ledger_write"
assert result["private_ledger_write"] is False
assert result["automatic_rule_mutation"] is False
assert result["eligible_forward_triggers"]==1
assert writer.write_calls==0
public=json.dumps(result,ensure_ascii=False)
assert raw["record_id"] not in public
assert "prev_hash" not in public and "record_hash" not in public

# System-status classification must keep outcome learning research-only.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"outcome.json"
    p.write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("playbook_outcome_shadow",p,datetime.now(timezone.utc))
    assert h["freshness"]=="fresh"
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.11 Outcome Foundation (shadow-only)" in workflow
assert "python scripts/playbook_outcome_engine.py" in workflow
assert "module_failure_marker.py playbook_outcome_foundation" in workflow
manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/playbook_outcome_shadow.json" in manifest
ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "Outcome Learning · Shadow Only" in ui
assert "样本不足时不展示胜率" in ui

print("PASS V6.11 Outcome Foundation shadow / definitions / baseline revalidation / no-ledger-write")
