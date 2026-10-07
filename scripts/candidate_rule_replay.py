#!/usr/bin/env python3
"""Candidate Rule Historical Replay v1.0.

Replays only fully reproducible Research/Shadow candidates from
research/registry/candidate_rules.json against the local historical archive.

This is historical post-compilation evidence only. It cannot satisfy Forward
maturity, Promotion, production, sizing, or trading requirements.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from local_history_agent import read_archive

ROOT=Path(__file__).resolve().parents[1]
CANDIDATES=ROOT/"research"/"registry"/"candidate_rules.json"
OUT=ROOT/"docs"/"research"/"candidate_rule_replay.json"
VERSION="1.0"
HORIZONS=(5,20,60)
PROVENANCE="historical_replay_post_candidate_compilation"
CLUSTER_SESSIONS=5

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def sma(series,window):
    return series.rolling(window,min_periods=window).mean()

def condition_series(df,cond):
    cid=str(cond.get("condition_id") or "")
    close=df["close"].astype(float)
    ma50=sma(close,50)
    if cid=="price_above_ma50":
        return close>ma50
    if cid=="price_below_ma50":
        return close<ma50
    if cid=="ma50_hold_two_sessions":
        above=close>ma50
        return above & above.shift(1).fillna(False)
    return None

def direction(candidate):
    role=str(candidate.get("state_role") or "")
    if role in {"trigger","confirmation"}:return "bullish"
    if role=="invalidation_or_risk":return "bearish"
    return None

def qqq_return(qqq,event_date,h):
    if qqq is None or qqq.empty:return None
    ts=pd.Timestamp(event_date)
    if ts not in qqq.index:return None
    loc=qqq.index.get_loc(ts)
    if not isinstance(loc,int) or loc+h>=len(qqq):return None
    a=finite(qqq.iloc[loc]["close"]);b=finite(qqq.iloc[loc+h]["close"])
    return None if a in (None,0) or b is None else b/a-1.0

def outcomes(df,pos,entry,qqq,event_date,expected):
    out={}
    for h in HORIZONS:
        if pos+h>=len(df):
            out[str(h)]=None;continue
        end=finite(df.iloc[pos+h]["close"])
        if end is None or not entry:
            out[str(h)]=None;continue
        path=df.iloc[pos+1:pos+h+1]
        lows=[finite(x) for x in path["low"].tolist()]
        highs=[finite(x) for x in path["high"].tolist()]
        lows=[x for x in lows if x is not None]
        highs=[x for x in highs if x is not None]
        ret=end/entry-1.0
        bench=qqq_return(qqq,event_date,h)
        out[str(h)]={
            "maturity_date":df.index[pos+h].date().isoformat(),
            "return":ret,
            "mae":min(lows)/entry-1.0 if lows else None,
            "mfe":max(highs)/entry-1.0 if highs else None,
            "benchmark_return":bench,
            "excess_vs_qqq":ret-bench if bench is not None else None,
            "aligned":ret>0 if expected=="bullish" else ret<0,
        }
    return out

def session_distance(index,a,b):
    try:
        ia=index.get_loc(pd.Timestamp(a));ib=index.get_loc(pd.Timestamp(b))
        if isinstance(ia,int) and isinstance(ib,int):return abs(ib-ia)
    except Exception:pass
    return 10**9

def effective_clusters(events,index):
    rows=sorted(events,key=lambda x:x["event_date"])
    if not rows:return []
    clusters=[[rows[0]]]
    for row in rows[1:]:
        if session_distance(index,clusters[-1][-1]["event_date"],row["event_date"])<=CLUSTER_SESSIONS:
            clusters[-1].append(row)
        else:
            clusters.append([row])
    return clusters

def avg(values):
    vals=[float(x) for x in values if x is not None and math.isfinite(float(x))]
    return None if not vals else sum(vals)/len(vals)

def replay_candidate(candidate,store):
    syms=list((candidate.get("scope") or {}).get("symbols") or [])
    if candidate.get("reproducibility_status")!="machine_ready_shadow":
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"candidate_not_fully_reproducible","events":[]}
    if len(syms)!=1:
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"single_symbol_scope_required","events":[]}
    expected=direction(candidate)
    if expected is None:
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"direction_not_explicit","events":[]}
    symbol=syms[0]
    df=store.get(symbol)
    if df is None or df.empty:
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"historical_symbol_missing","events":[]}
    df=df.sort_index()
    df=df[~df.index.duplicated(keep="last")]
    needed=[]
    for cond in candidate.get("conditions") or []:
        series=condition_series(df,cond)
        if series is None:
            return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"unsupported_replay_condition","events":[]}
        needed.append(series.fillna(False))
    if not needed:
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"no_replay_conditions","events":[]}
    active=needed[0].copy()
    for s in needed[1:]:active=active & s
    qqq=store.get("QQQ")
    events=[]
    prev=False
    for i,flag in enumerate(active.tolist()):
        flag=bool(flag)
        if flag and not prev:
            entry=finite(df.iloc[i]["close"])
            if entry:
                day=df.index[i].date().isoformat()
                events.append({
                    "candidate_id":candidate.get("candidate_id"),
                    "symbol":symbol,
                    "event_date":day,
                    "expected_direction":expected,
                    "baseline_close":entry,
                    "evidence_provenance":PROVENANCE,
                    "outcomes":outcomes(df,i,entry,qqq,day,expected),
                })
        prev=flag
    clusters=effective_clusters(events,df.index)
    stats={}
    for h in HORIZONS:
        mature=[e["outcomes"].get(str(h)) for e in events if e["outcomes"].get(str(h))]
        aligned=sum(1 for x in mature if x.get("aligned"))
        stats[str(h)]={
            "raw_n":len(mature),
            "effective_n":sum(1 for cl in clusters if any(e["outcomes"].get(str(h)) for e in cl)),
            "aligned_rate":aligned/len(mature) if mature else None,
            "avg_return":avg([x.get("return") for x in mature]),
            "avg_mae":avg([x.get("mae") for x in mature]),
            "avg_mfe":avg([x.get("mfe") for x in mature]),
            "avg_excess_vs_qqq":avg([x.get("excess_vs_qqq") for x in mature]),
        }
    return {
        "candidate_id":candidate.get("candidate_id"),
        "status":"replayed",
        "symbol":symbol,
        "method_family":candidate.get("method_family"),
        "expected_direction":expected,
        "raw_events":len(events),
        "effective_clusters":len(clusters),
        "statistics":stats,
        "events":events[:80],
    }

def build(registry,store):
    rows=[replay_candidate(c,store) for c in (registry.get("candidates") or [])]
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"research_shadow_historical_only",
        "evidence_provenance":PROVENANCE,
        "forward_evidence_mixed":False,
        "automatic_promotion":False,
        "production_effect":"none",
        "summary":{
            "candidates":len(rows),
            "replayed":sum(1 for x in rows if x.get("status")=="replayed"),
            "blocked":sum(1 for x in rows if x.get("status")=="blocked"),
            "raw_events":sum(int(x.get("raw_events") or 0) for x in rows),
            "effective_clusters":sum(int(x.get("effective_clusters") or 0) for x in rows),
        },
        "candidates":rows,
        "guardrails":[
            "Historical replay is post-candidate-compilation evidence and never Forward evidence.",
            "Only fully reproducible candidate conditions are replayed.",
            "State-entry events are counted; repeated days inside one state are not new events.",
            "Signals within five sessions are clustered for effective-N reporting.",
            "Replay cannot write Promotion Gate, protected rules, positions, sizing or orders.",
        ],
    }

def main():
    out=build(load(CANDIDATES,{"candidates":[]}),read_archive())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["summary"],ensure_ascii=False))

if __name__=="__main__":main()
