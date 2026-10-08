#!/usr/bin/env python3
"""Benchmark-adjusted outcome memory for canonical event/news evidence.

Descriptive attribution only: temporal association is not causation.
"""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
EVENT_DIR=ROOT/"research"/"archive"/"events"
OUTCOMES=ROOT/"research"/"archive"/"event_outcomes.jsonl"
OUT=ROOT/"docs"/"research"/"event_outcome_memory.json"
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

def event_rows():
    rows=[]
    if not EVENT_DIR.exists():return rows
    for p in EVENT_DIR.glob("*.jsonl"):rows.extend(read_jsonl(p))
    return rows

def append_unique(rows):
    OUTCOMES.parent.mkdir(parents=True,exist_ok=True)
    known={str(x.get("outcome_id")) for x in read_jsonl(OUTCOMES)}
    added=0
    with OUTCOMES.open("a",encoding="utf-8") as f:
        for r in rows:
            oid=str(r.get("outcome_id") or "")
            if not oid or oid in known:continue
            f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n")
            known.add(oid);added+=1
    return added

def mature(event,df,bdf,h):
    if df is None or df.empty or bdf is None or bdf.empty:return None
    date_text=str(event.get("published_at") or event.get("event_date") or "")[:10]
    try:day=pd.Timestamp(date_text)
    except Exception:return None
    fut=df[df.index>day].sort_index().head(h)
    bfut=bdf[bdf.index>day].sort_index().head(h)
    if len(fut)<h or len(bfut)<h:return None
    start=float(fut["close"].iloc[0]);end=float(fut["close"].iloc[-1])
    bstart=float(bfut["close"].iloc[0]);bend=float(bfut["close"].iloc[-1])
    ret=(end/start-1)*100;bret=(bend/bstart-1)*100
    return {
      "outcome_id":f"{event.get('archive_id')}:{h}",
      "archive_id":event.get("archive_id"),"symbol":event.get("symbol"),
      "published_at":event.get("published_at"),"title":event.get("title"),
      "publisher":event.get("publisher"),"source_type":event.get("source_type"),
      "source_priority":event.get("source_priority"),
      "horizon_sessions":h,"horizon_end":str(fut.index[-1])[:10],
      "return_pct":ret,"benchmark_return_pct":bret,"excess_return_pct":ret-bret,
      "mae_pct":(float(fut["low"].min())/start-1)*100,
      "mfe_pct":(float(fut["high"].max())/start-1)*100,
      "benchmark_symbol":"SPY" if getattr(bdf,"attrs",{}).get("_symbol")=="SPY" else "QQQ",
      "causal_claim":False,"production_effect":"none",
      "matured_at":datetime.now(timezone.utc).isoformat(),
    }

def run(histories=None):
    histories=histories if histories is not None else read_archive()
    benchmark_symbol="SPY" if histories.get("SPY") is not None else "QQQ"
    bdf=histories.get(benchmark_symbol)
    if bdf is not None:
        try:bdf.attrs["_symbol"]=benchmark_symbol
        except Exception:pass
    matured=[]
    for event in event_rows():
        symbol=str(event.get("symbol") or "")
        if not symbol or symbol not in histories:continue
        for h in HORIZONS:
            x=mature(event,histories.get(symbol),bdf,h)
            if x:matured.append(x)
    added=append_unique(matured)
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
      "counts":{"events":len(event_rows()),"outcomes":len(all_rows),"outcomes_added":added},
      "benchmark":benchmark_symbol,"horizons":score,
      "guardrails":[
        "Outcome windows start after the event publication date; no future data is used in the event snapshot.",
        "Benchmark-adjusted association is descriptive and never treated as proof that the news caused the move.",
        "Media evidence cannot outrank SEC/IR facts and cannot directly mutate Production rules."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False))
