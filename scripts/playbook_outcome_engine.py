#!/usr/bin/env python3
"""V6.11 Outcome Foundation (shadow mode).

Reads private Forward Trigger records, revalidates their recorded baseline
against local daily history, and computes 5/20/60-session outcome candidates.

During the V6.10 stabilization window this module is deliberately read-only
with respect to the private Forward Ledger: it publishes only a sanitized
aggregate status file and does not create an Outcome stream.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

from local_history_agent import read_archive
from private_ledger import PrivateGitHubLedger, verify_records, ZERO_HASH

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"config"/"playbook_outcomes.json"
OUT=ROOT/"docs"/"research"/"playbook_outcome_shadow.json"
PLAYBOOK_STATUS=ROOT/"docs"/"research"/"playbook_status.json"
VERSION="6.11.0-shadow"

def load(path, default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def month_keys(anchor_date, months_back=4):
    if isinstance(anchor_date,str):anchor_date=date.fromisoformat(anchor_date[:10])
    y,m=anchor_date.year,anchor_date.month
    out=[]
    for _ in range(months_back+1):
        out.append(f"{y:04d}-{m:02d}")
        m-=1
        if m==0:y-=1;m=12
    return sorted(out)

def read_private_records(writer, stream, market_date, months_back=4):
    if writer is None:return [],[]
    records=[];problems=[]
    for month in month_keys(market_date,months_back):
        text,_=writer.read_text(f"ledger/{stream}/{month}.jsonl")
        rows=[]
        for line in text.splitlines():
            if not line.strip():continue
            try:rows.append(json.loads(line))
            except Exception:
                problems.append(f"{stream}:{month}:invalid_json")
        if not rows:continue
        initial=rows[0].get("prev_hash") or ZERO_HASH
        ok,meta=verify_records(rows,initial)
        if not ok:
            problems.append(f"{stream}:{month}:chain_{meta.get('reason')}")
            continue
        records.extend(rows)
    return records,problems

def outcome_asset(event, definition):
    spec=definition.get("evaluation_asset")
    return event.get("symbol") if spec=="event_symbol" else spec

def direction_for(event, definition):
    return (definition.get("expected_direction_by_detail") or {}).get(event.get("state_detail"))

def _loc(df, day):
    try:
        ts=pd.Timestamp(str(day)[:10])
        if ts in df.index:return df.index.get_loc(ts)
    except Exception:pass
    return None

def benchmark_return(store, benchmark, event_date, horizon):
    if not benchmark:return None
    df=store.get(benchmark)
    if df is None or df.empty:return None
    pos=_loc(df,event_date)
    if pos is None or not isinstance(pos,int) or pos+horizon>=len(df):return None
    entry=finite(df.iloc[pos]["close"]);end=finite(df.iloc[pos+horizon]["close"])
    return None if not entry or end is None else end/entry-1.0

def score_event(event, definition, store, horizons, tolerance):
    asset=outcome_asset(event,definition)
    direction=direction_for(event,definition)
    result={
        "playbook_id":event.get("playbook_id"),
        "state_detail":event.get("state_detail"),
        "evaluation_asset":asset,
        "objective_group":(definition.get("objective_group_by_detail") or {}).get(event.get("state_detail")),
        "expected_direction":direction,
        "baseline_check":"pending",
        "outcomes":{},
    }
    if not asset or not direction:
        result["baseline_check"]="definition_missing"
        return result
    df=store.get(asset)
    if df is None or df.empty:
        result["baseline_check"]="history_missing"
        return result
    pos=_loc(df,event.get("event_date") or event.get("market_date"))
    if pos is None or not isinstance(pos,int):
        result["baseline_check"]="baseline_session_missing"
        return result
    recorded=finite(event.get("baseline_close"))
    historical=finite(df.iloc[pos]["close"])
    if recorded is None or historical is None or recorded<=0:
        result["baseline_check"]="baseline_price_missing"
        return result
    gap=abs(historical/recorded-1.0)
    result["baseline_gap"]=gap
    if gap>tolerance:
        result["baseline_check"]="baseline_mismatch"
        return result
    result["baseline_check"]="pass"
    for h in horizons:
        key=str(h)
        if pos+h>=len(df):
            result["outcomes"][key]=None
            continue
        end=finite(df.iloc[pos+h]["close"])
        if end is None:
            result["outcomes"][key]=None
            continue
        path=df.iloc[pos+1:pos+h+1]
        ret=end/recorded-1.0
        lows=[finite(x) for x in path["low"].tolist()]
        highs=[finite(x) for x in path["high"].tolist()]
        lows=[x for x in lows if x is not None];highs=[x for x in highs if x is not None]
        mae=min(lows)/recorded-1.0 if lows else None
        mfe=max(highs)/recorded-1.0 if highs else None
        bench=benchmark_return(store,definition.get("benchmark"),event.get("event_date") or event.get("market_date"),h)
        aligned=(ret>0) if direction=="bullish" else (ret<0)
        result["outcomes"][key]={
            "mature":True,
            "return":ret,
            "mae":mae,
            "mfe":mfe,
            "benchmark_return":bench,
            "excess_vs_benchmark":ret-bench if bench is not None else None,
            "aligned":bool(aligned),
            "maturity_date":df.index[pos+h].date().isoformat(),
        }
    return result

def aggregate(scored, horizons):
    by_playbook={}
    for row in scored:
        pid=row.get("playbook_id") or "UNKNOWN"
        slot=by_playbook.setdefault(pid,{
            "trigger_records":0,
            "baseline_pass":0,
            "baseline_mismatch":0,
            "history_or_definition_missing":0,
            "horizons":{str(h):{"mature":0,"aligned":0,"not_aligned":0,"pending":0} for h in horizons},
            "objective_groups":{},
        })
        slot["trigger_records"]+=1
        check=row.get("baseline_check")
        if check=="pass":slot["baseline_pass"]+=1
        elif check=="baseline_mismatch":slot["baseline_mismatch"]+=1
        else:slot["history_or_definition_missing"]+=1
        group=row.get("objective_group")
        if group:slot["objective_groups"][group]=slot["objective_groups"].get(group,0)+1
        for h in horizons:
            out=(row.get("outcomes") or {}).get(str(h))
            hs=slot["horizons"][str(h)]
            if not out:hs["pending"]+=1
            else:
                hs["mature"]+=1
                if out.get("aligned"):hs["aligned"]+=1
                else:hs["not_aligned"]+=1
    return by_playbook

def build(writer=None, store=None, market_date=None, now=None):
    now=now or datetime.now(timezone.utc)
    config=load(CONFIG,{})
    horizons=[int(x) for x in config.get("horizons") or [5,20,60]]
    tolerance=float(config.get("baseline_revalidation_tolerance") or 0.03)
    defs=config.get("definitions") or {}
    if not market_date:
        status=load(PLAYBOOK_STATUS,{})
        market_date=status.get("market_date") or now.date().isoformat()
    writer=writer if writer is not None else PrivateGitHubLedger.from_env()
    store=read_archive() if store is None else store

    records,ledger_problems=read_private_records(writer,"trigger",market_date,4)
    eligible=[
        x for x in records
        if x.get("record_type")=="trigger_state_event"
        and x.get("scoreable") is True
        and x.get("evidence_provenance")=="forward_out_of_sample"
    ]
    scored=[score_event(x,defs.get(x.get("playbook_id")) or {},store,horizons,tolerance) for x in eligible]
    summary=aggregate(scored,horizons)
    mature_total={str(h):sum((x.get("horizons") or {}).get(str(h),{}).get("mature",0) for x in summary.values()) for h in horizons}
    pending_total={str(h):sum((x.get("horizons") or {}).get(str(h),{}).get("pending",0) for x in summary.values()) for h in horizons}
    return {
        "version":VERSION,
        "generated_at":now.astimezone(timezone.utc).isoformat(),
        "mode":"shadow_no_forward_ledger_write",
        "market_date":str(market_date)[:10],
        "storage_configured":bool(writer),
        "private_trigger_records":len(records),
        "eligible_forward_triggers":len(eligible),
        "ledger_read_problems":ledger_problems,
        "mature_total":mature_total,
        "pending_total":pending_total,
        "by_playbook":summary,
        "outcome_definitions":{
            pid:{
                "evaluation_asset":d.get("evaluation_asset"),
                "benchmark":d.get("benchmark"),
                "success_basis":d.get("success_basis"),
                "interpretation":d.get("interpretation"),
            } for pid,d in defs.items()
        },
        "guardrails":config.get("guardrails") or [],
        "private_ledger_write":False,
        "automatic_rule_mutation":False,
    }

def main():
    market=os.getenv("MYALPHA_MARKET_DATE") or None
    result=build(market_date=market)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "version":result["version"],
        "mode":result["mode"],
        "eligible_forward_triggers":result["eligible_forward_triggers"],
        "mature_total":result["mature_total"],
        "ledger_read_problems":result["ledger_read_problems"],
    },ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
