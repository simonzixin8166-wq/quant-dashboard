import copy
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import playbook_engine as pe
import private_ledger as pl

def asset(close=100,prev=99,date="2026-10-02",**extra):
    row={"date":date,"close":close,"prev_close":prev,"ath_validation":"PASS","strategy_drawdown":-0.01,"level":0}
    row.update(extra);return row

def snapshot(day, vgt_level=0, vgt_close=120, vgt_prev=119, vgt_ok=True):
    data={
      "spy_date":day,
      "core":{
        "QQQM":asset(close=90,prev=91,date=day,strategy_drawdown=-0.01,level=0),
        "VGT":asset(close=vgt_close,prev=vgt_prev,date=day,strategy_drawdown=-0.02 if vgt_level==0 else -0.16,level=vgt_level),
        "QLD":asset(close=80,prev=79,date=day,strategy_drawdown=-0.04,level=0),
      },
      "index":{
        "QQQ":asset(close=700,prev=695,date=day),
        "SMH":asset(close=600,prev=590,date=day),
        "TQQQ":asset(close=80,prev=79,date=day),
      },
      "tqqq_x2":{
        "available":True,"date":day,"rule":"hold","target_position":100,"target_daily_exposure":2.0,
        "snapshot":{"date":day,"qqq":700,"vix":18},
      },
      "leaps_radar":{"assets":[
        {"symbol":"QQQ","available":True,"date":day,"close":700,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
        {"symbol":"SMH","available":True,"date":day,"close":600,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
        {"symbol":"VGT","available":True,"date":day,"close":vgt_close,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
      ]},
    }
    if not vgt_ok:
        data["core"]["VGT"]["ath_validation"]="FAIL"
    return data

class FakeWriter:
    def __init__(self):self.calls=[]
    def append_many(self,stream,records,market_date):
        self.calls.append((stream,[dict(x) for x in records],market_date))
        head=("f"*64) if records else pl.ZERO_HASH
        return pl.AppendResult(stream,f"ledger/{stream}/{market_date[:7]}.jsonl",bool(records),len(records),len(records),head)

def run_at(day, data, pe_paths, history, hour=21):
    pe.DATA.write_text(json.dumps(data),encoding="utf-8")
    writer=FakeWriter()
    now=datetime.fromisoformat(day+"T"+f"{hour:02d}:30:00+00:00")
    status,_=pe.build(now=now,writer=writer)
    return status,writer

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    old_paths=(pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT)
    try:
        pe.DATA=td/"data.json";pe.HISTORY=td/"history.json";pe.STATUS_OUT=td/"status.json";pe.ANCHOR_OUT=td/"anchor.json"
        history={"update":{"quarantined":[]}}
        pe.HISTORY.write_text(json.dumps(history),encoding="utf-8")

        # 10/02 valid baseline: VGT normal.
        s0,w0=run_at("2026-10-02",snapshot("2026-10-02",0),old_paths,history)
        assert [r for st,rows,_ in w0.calls if st=="trigger" for r in rows]==[]

        # 10/05 VGT becomes UNDETERMINED due failed adjusted-ATH validation.
        s1,w1=run_at("2026-10-05",snapshot("2026-10-05",0,vgt_ok=False),old_paths,history)
        v1=next(x for x in s1["playbooks"] if x["entity_key"]=="CP-01:VGT")
        assert v1["state"]=="UNDETERMINED"
        assert v1["last_valid_market_date"]=="2026-10-02"
        assert v1["unknown_since_market_date"]=="2026-10-05"
        assert v1["late_detected"] is False
        assert [r for st,rows,_ in w1.calls if st=="trigger" for r in rows if r.get("entity_key")=="CP-01:VGT"]==[]

        # 10/06 data recovers and VGT is tier1. Detection is on 10/06, never backfilled to 10/05.
        s2,w2=run_at("2026-10-06",snapshot("2026-10-06",1),old_paths,history)
        v2=next(x for x in s2["playbooks"] if x["entity_key"]=="CP-01:VGT")
        assert v2["state"]=="TRIGGERED"
        assert v2["late_detected"] is True
        assert v2["detection_delay_sessions"]==1
        assert v2["timing_uncertain"] is True
        assert v2["last_valid_market_date"]=="2026-10-06"

        triggers=[r for st,rows,_ in w2.calls if st=="trigger" for r in rows if r.get("entity_key")=="CP-01:VGT"]
        assert len(triggers)==1
        ev=triggers[0]
        assert ev["event_date"]=="2026-10-06"
        assert ev["market_date"]=="2026-10-06"
        assert ev["late_detected"] is True
        assert ev["detection_delay_sessions"]==1
        assert ev["timing_uncertain"] is True
        assert ev["detection_window_start"]=="2026-10-05"
        assert ev["detection_window_end"]=="2026-10-06"
        assert ev["previous_valid_market_date"]=="2026-10-02"
        assert ev["previous_valid_state_key"]=="IDLE:normal"
        assert ev["scoreable"] is True
        assert ev["evidence_provenance"]=="forward_out_of_sample"

        audits=[r for st,rows,_ in w2.calls if st=="audit" for r in rows]
        late=[r for r in audits if r.get("kind")=="late_detection_window" and r.get("entity_key")=="CP-01:VGT"]
        assert len(late)==1
        assert late[0]["timing_uncertain"] is True
        assert late[0]["scoreable"] is False

        # Continuous valid data has no artificial delay.
        s3,w3=run_at("2026-10-07",snapshot("2026-10-07",0),old_paths,history)
        events=[r for st,rows,_ in w3.calls if st=="trigger" for r in rows if r.get("entity_key")=="CP-01:VGT"]
        assert len(events)==1
        assert events[0]["event_date"]=="2026-10-07"
        assert events[0]["late_detected"] is False
        assert events[0]["detection_delay_sessions"]==0
        assert events[0]["timing_uncertain"] is False
    finally:
        pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT=old_paths

print("PASS V6.10 late detection integrity / actual discovery date / uncertainty / no backfill")
