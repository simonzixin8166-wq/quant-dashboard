import copy
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import playbook_engine as pe
import private_ledger as pl
import playbook_watchdog as wd
import system_status_center as ssc

def asset(close=100,prev=99,date="2026-10-02",**extra):
    row={"date":date,"close":close,"prev_close":prev,"ath_validation":"PASS","strategy_drawdown":-0.01,"level":0}
    row.update(extra);return row

data={
 "spy_date":"2026-10-02",
 "core":{
   "QQQM":asset(close=90,prev=91,strategy_drawdown=-0.01,level=0),
   "VGT":asset(close=120,prev=119,strategy_drawdown=-0.02,level=0),
   "QLD":asset(close=80,prev=79,strategy_drawdown=-0.04,level=0),
 },
 "index":{
   "QQQ":asset(close=700,prev=695),
   "SMH":asset(close=600,prev=590),
   "TQQQ":asset(close=80,prev=79),
 },
 "tqqq_x2":{
   "available":True,"date":"2026-10-02","rule":"tier1","target_position":33,"target_daily_exposure":0.99,
   "snapshot":{"date":"2026-10-02","qqq":700,"vix":21},
 },
 "leaps_radar":{"assets":[
   {"symbol":"QQQ","available":True,"date":"2026-10-02","close":700,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
   {"symbol":"SMH","available":True,"date":"2026-10-02","close":600,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
   {"symbol":"VGT","available":True,"date":"2026-10-02","close":120,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
 ]},
}
history={"update":{"quarantined":[]}}
now=datetime(2026,10,3,12,0,tzinfo=timezone.utc)

# Repository-variable compatible switches must preserve defaults and allow per-playbook pause.
old_env={k:os.environ.get(k) for k in ("MYALPHA_CP_01_LEDGER_ENABLED","MYALPHA_CP_02_LEDGER_ENABLED","MYALPHA_CP_03_LEDGER_ENABLED")}
try:
    os.environ["MYALPHA_CP_02_LEDGER_ENABLED"]="false"
    switches=pe.runtime_switches()
    assert switches["CP-01"]["ledger_enabled"] is True
    assert switches["CP-02"]["ledger_enabled"] is False
    assert switches["CP-03"]["ledger_enabled"] is True
finally:
    for k,v in old_env.items():
        if v is None:os.environ.pop(k,None)
        else:os.environ[k]=v

class FakeWriter:
    def __init__(self):self.calls=[]
    def append_many(self,stream,records,market_date):
        self.calls.append((stream,[dict(x) for x in records],market_date))
        head=("f"*64) if records else pl.ZERO_HASH
        return pl.AppendResult(stream,f"ledger/{stream}/{market_date[:7]}.jsonl",bool(records),len(records),len(records),head)

# A paused playbook still evaluates visibly, but its state transition is not scoreable or written as a trigger.
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    old_paths=(pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT)
    old_var=os.environ.get("MYALPHA_CP_02_LEDGER_ENABLED")
    try:
        pe.DATA=td/"data.json";pe.HISTORY=td/"history.json";pe.STATUS_OUT=td/"status.json";pe.ANCHOR_OUT=td/"anchor.json"
        pe.DATA.write_text(json.dumps(data),encoding="utf-8")
        pe.HISTORY.write_text(json.dumps(history),encoding="utf-8")
        _,baseline_rows=pe.evaluate(data,history,now)
        prior=[]
        for row in baseline_rows:
            x=copy.deepcopy(row);x["committed_state_key"]=x["state_key"];prior.append(x)
        # Prior CP-02 was hold/IDLE, current data is tier1/TRIGGERED.
        for x in prior:
            if x["playbook_id"]=="CP-02":
                x["state"]="IDLE";x["detail"]="hold";x["state_key"]="IDLE:hold";x["committed_state_key"]="IDLE:hold"
        pe.STATUS_OUT.write_text(json.dumps({"storage":{"forward_clock_active":True},"kill_switch":{"per_playbook":{}},"playbooks":prior}),encoding="utf-8")
        os.environ["MYALPHA_CP_02_LEDGER_ENABLED"]="false"
        writer=FakeWriter()
        status,_=pe.build(now=now,writer=writer)
        cp02=next(x for x in status["playbooks"] if x["playbook_id"]=="CP-02")
        assert cp02["transition_detected"] is True
        assert cp02["suppressed_by_kill_switch"] is True
        assert cp02["runtime"]["ledger_active"] is False
        triggers=[r for stream,rows,_ in writer.calls if stream=="trigger" for r in rows if r.get("playbook_id")=="CP-02"]
        assert triggers==[]
        audits=[r for stream,rows,_ in writer.calls if stream=="audit" for r in rows]
        assert any(r.get("kind")=="transition_suppressed_by_kill_switch" and r.get("playbook_id")=="CP-02" for r in audits)
    finally:
        pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT=old_paths
        if old_var is None:os.environ.pop("MYALPHA_CP_02_LEDGER_ENABLED",None)
        else:os.environ["MYALPHA_CP_02_LEDGER_ENABLED"]=old_var

# Independent watchdog uses expected completed trading session, not wall-clock date.
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    old_paths=(wd.STATUS,wd.ANCHOR,wd.FAILURES)
    try:
        wd.STATUS=td/"status.json";wd.ANCHOR=td/"anchor.json";wd.FAILURES=td/"failures.json"
        wd.STATUS.write_text(json.dumps({"market_date":"2026-10-02","generated_at":"2026-10-03T01:00:00+00:00","heartbeat":{"status":"pass"},"storage":{"forward_clock_active":True}}),encoding="utf-8")
        wd.ANCHOR.write_text(json.dumps({"status":"ok"}),encoding="utf-8")
        wd.FAILURES.write_text(json.dumps({"modules":{}}),encoding="utf-8")
        assert wd.check(now)["ok"] is True
        wd.STATUS.write_text(json.dumps({"market_date":"2026-10-01","generated_at":"2026-10-03T01:00:00+00:00","heartbeat":{"status":"pass"},"storage":{"forward_clock_active":True}}),encoding="utf-8")
        bad=wd.check(now)
        assert bad["ok"] is False and any("market_date_stale" in x for x in bad["problems"])
    finally:
        wd.STATUS,wd.ANCHOR,wd.FAILURES=old_paths

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "continue-on-error: true" in workflow
assert "module_failure_marker.py playbook_engine" in workflow
assert "vars.MYALPHA_CP_02_LEDGER_ENABLED" in workflow
watch=(ROOT/".github/workflows/playbook-watchdog.yml").read_text(encoding="utf-8")
assert "Playbook Independent Watchdog" in watch
assert "python scripts/playbook_watchdog.py" in watch
assert "Playbook Independent Watchdog" in ssc.WATCH_WORKFLOWS["quant-dashboard"]

print("PASS V6.10 stabilization P1 / failure isolation / watchdog / per-playbook kill switches")
