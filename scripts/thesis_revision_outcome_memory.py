#!/usr/bin/env python3
"""Outcome memory for immutable Auto Thesis revisions.

Each thesis revision is frozen at revision_at. Future 5/20/60-session returns
are evaluated only after that timestamp, benchmark-adjusted and explicitly
non-causal. This is research evaluation only and cannot mutate Production rules.
"""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV_DIR=ROOT/"research"/"archive"/"thesis_revisions"
OUTCOMES=ROOT/"research"/"archive"/"thesis_revision_outcomes.jsonl"
OUT=ROOT/"docs"/"research"/"thesis_revision_outcome_memory.json"
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive

HORIZONS=(5,20,60)

def read_jsonl(path):
    rows=[]
    p=Path(path)
    if not p.exists():return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        try:rows.append(json.loads(line))
        except Exception:pass
    return rows

def revisions():
    rows=[]
    if not REV_DIR.exists():return rows
    for p in REV_DIR.glob("*.jsonl"):
        rows.extend(read_jsonl(p))
    return rows

def rid(row):
    return f"{row.get('symbol')}|{row.get('revision_at')}|{row.get('evidence_hash')}"

def append_unique(rows):
    OUTCOMES.parent.mkdir(parents=True,exist_ok=True)
    known={str(x.get("outcome_id")) for x in read_jsonl(OUTCOMES)}
    added=0
    with OUTCOMES.open("a",encoding="utf-8") as f:
        for row in rows:
            oid=str(row.get("outcome_id") or "")
            if not oid or oid in known:continue
            f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
            known.add(oid);added+=1
    return added

def mature(rev,df,bdf,h):
    if df is None or df.empty or bdf is None or bdf.empty:return None
    try:
        ts=pd.Timestamp(str(rev.get("revision_at") or ""))
        if ts.tzinfo is not None: ts=ts.tz_convert(None)
        day=ts.normalize()
    except Exception:return None
    fut=df[df.index>day].sort_index().head(h)
    bfut=bdf[bdf.index>day].sort_index().head(h)
    if len(fut)<h or len(bfut)<h:return None
    start=float(fut["close"].iloc[0]);end=float(fut["close"].iloc[-1])
    bstart=float(bfut["close"].iloc[0]);bend=float(bfut["close"].iloc[-1])
    ret=(end/start-1)*100;bret=(bend/bstart-1)*100
    return {
      "outcome_id":f"{rid(rev)}:{h}",
      "symbol":rev.get("symbol"),"revision_at":rev.get("revision_at"),
      "evidence_hash":rev.get("evidence_hash"),"previous_evidence_hash":rev.get("previous_evidence_hash"),
      "change_reason":rev.get("change_reason"),"horizon_sessions":h,
      "horizon_end":str(fut.index[-1])[:10],
      "return_pct":ret,"benchmark_return_pct":bret,"excess_return_pct":ret-bret,
      "mae_pct":(float(fut["low"].min())/start-1)*100,
      "mfe_pct":(float(fut["high"].max())/start-1)*100,
      "benchmark_symbol":getattr(bdf,"attrs",{}).get("_symbol","QQQ"),
      "causal_claim":False,"production_effect":"none",
      "matured_at":datetime.now(timezone.utc).isoformat(),
    }

def run(histories=None):
    histories=histories if histories is not None else read_archive()
    benchmark="SPY" if histories.get("SPY") is not None else "QQQ"
    bdf=histories.get(benchmark)
    if bdf is not None:
        try:bdf.attrs["_symbol"]=benchmark
        except Exception:pass
    new=[]
    for rev in revisions():
        symbol=str(rev.get("symbol") or "")
        if not symbol or histories.get(symbol) is None:continue
        for h in HORIZONS:
            row=mature(rev,histories.get(symbol),bdf,h)
            if row:new.append(row)
    added=append_unique(new)
    all_rows=read_jsonl(OUTCOMES)
    score={}
    for h in HORIZONS:
        rows=[x for x in all_rows if int(x.get("horizon_sessions") or 0)==h]
        score[str(h)]={
          "n":len(rows),
          "avg_excess_return_pct":sum(float(x["excess_return_pct"]) for x in rows)/len(rows) if rows else None,
          "positive_excess_rate":sum(float(x["excess_return_pct"])>0 for x in rows)/len(rows) if rows else None,
        }
    out={
      "version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "status":"learning_active" if all_rows else "waiting_for_mature_outcomes",
      "counts":{"revisions":len(revisions()),"outcomes":len(all_rows),"outcomes_added":added},
      "benchmark":benchmark,"horizons":score,
      "guardrails":[
        "Outcome windows begin strictly after revision_at; no future data enters the thesis snapshot.",
        "Benchmark-adjusted association evaluates thesis-revision follow-through but is not proof of causality.",
        "Outcome memory is research-only and cannot change Production thresholds without governed promotion."
      ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False))
