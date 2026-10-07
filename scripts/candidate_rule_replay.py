#!/usr/bin/env python3
"""Candidate Rule Historical Replay v1.1.

Research/Shadow-only historical replay for compiled candidate rules.

Safety:
- historical replay never becomes Forward evidence;
- only fully machine-reproducible candidates can replay;
- missing symbols may be fetched on demand from STOOQ for research replay only;
- signals use same-day/past data only; future bars are used only for outcomes;
- no Promotion Gate, protected rule, sizing, position, or order is modified.
"""
from __future__ import annotations

import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf

try:
    from local_history_agent import read_archive
except ModuleNotFoundError:
    from scripts.local_history_agent import read_archive

ROOT=Path(__file__).resolve().parents[1]
CANDIDATES=ROOT/"research"/"registry"/"candidate_rules.json"
OUT=ROOT/"docs"/"research"/"candidate_rule_replay.json"
VERSION="1.1"
HORIZONS=(5,20,60)
PROVENANCE="historical_replay_post_candidate_compilation"
CLUSTER_SESSIONS=5
STOOQ_URL="https://stooq.com/q/d/l/?s={symbol}.us&i=d"

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def normalize_history(df):
    if df is None or df.empty:return None
    x=df.copy()
    x.columns=[str(c).strip().lower() for c in x.columns]
    if "date" in x.columns:
        x["date"]=pd.to_datetime(x["date"],errors="coerce")
        x=x.dropna(subset=["date"]).set_index("date")
    x.index=pd.to_datetime(x.index,errors="coerce")
    x=x[~x.index.isna()]
    need=["open","high","low","close"]
    if not all(c in x.columns for c in need):return None
    if "volume" not in x.columns:x["volume"]=0
    for c in need+["volume"]:x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.dropna(subset=need)
    x=x[(x[need]>0).all(axis=1)]
    x=x.sort_index()
    return x[~x.index.duplicated(keep="last")]

def fetch_research_history(symbol):
    """Research-only fallback chain: STOOQ first, yfinance second.

    Neither provider becomes a Production dependency. The exact provider is
    returned for audit provenance. Failure remains explicit and fail-closed.
    """
    errors=[]
    try:
        url=STOOQ_URL.format(symbol=str(symbol).lower().replace(".","-"))
        req=Request(url,headers={"User-Agent":"MyAlphaView/6.9 research-shadow replay"})
        with urlopen(req,timeout=20) as resp:
            raw=resp.read()
        out=normalize_history(pd.read_csv(io.BytesIO(raw)))
        if out is not None and len(out)>=220:
            return out,"stooq_on_demand_research_only"
        errors.append("stooq_history_insufficient")
    except Exception as exc:
        errors.append("stooq:"+str(exc)[:100])
    try:
        raw=yf.download(symbol,period="10y",auto_adjust=False,progress=False,threads=False,actions=False)
        if isinstance(raw.columns,pd.MultiIndex):
            try:
                if symbol in raw.columns.get_level_values(-1):
                    raw=raw.xs(symbol,axis=1,level=-1,drop_level=True)
                elif symbol in raw.columns.get_level_values(0):
                    raw=raw.xs(symbol,axis=1,level=0,drop_level=True)
            except Exception:
                pass
        out=normalize_history(raw)
        if out is not None and len(out)>=220:
            return out,"yfinance_on_demand_research_only"
        errors.append("yfinance_history_insufficient")
    except Exception as exc:
        errors.append("yfinance:"+str(exc)[:100])
    raise ValueError("; ".join(errors)[:240])

def fetch_stooq_history(symbol):
    """Backward-compatible helper retained for tests/importers."""
    df,_=fetch_research_history(symbol)
    return df

def required_symbols(registry):
    syms={"QQQ"}
    for c in registry.get("candidates") or []:
        if c.get("reproducibility_status")!="machine_ready_shadow":continue
        for s in (c.get("scope") or {}).get("symbols") or []:
            if s:syms.add(str(s).upper())
    return sorted(syms)

def resolve_store(registry,base_store=None,fetcher=fetch_research_history):
    store={str(k).upper():normalize_history(v) for k,v in (base_store or {}).items()}
    provenance={}
    for s in list(store):
        if store[s] is not None and not store[s].empty:
            provenance[s]={"source":"local_stooq_archive","status":"ready","rows":len(store[s])}
    for symbol in required_symbols(registry):
        if store.get(symbol) is not None and not store[symbol].empty:continue
        try:
            fetched=fetcher(symbol)
            if isinstance(fetched,tuple):
                df,provider=fetched
            else:
                df,provider=fetched,"test_or_custom_research_provider"
            store[symbol]=df
            provenance[symbol]={"source":provider,"status":"ready","rows":len(df)}
        except Exception as exc:
            provenance[symbol]={"source":"research_on_demand_fallback_chain","status":"blocked","reason":str(exc)[:240]}
    return store,provenance

def sma(series,window):
    return series.rolling(window,min_periods=window).mean()

def condition_series(df,cond):
    cid=str(cond.get("condition_id") or "")
    close=df["close"].astype(float)
    ma50=sma(close,50)
    if cid=="price_above_ma50":return close>ma50
    if cid=="price_below_ma50":return close<ma50
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

def event_regime(qqq,event_date):
    if qqq is None or qqq.empty:return "unknown"
    ts=pd.Timestamp(event_date)
    if ts not in qqq.index:return "unknown"
    loc=qqq.index.get_loc(ts)
    if not isinstance(loc,int) or loc<199:return "unknown"
    close=finite(qqq.iloc[loc]["close"])
    ma200=finite(qqq["close"].astype(float).iloc[:loc+1].rolling(200,min_periods=200).mean().iloc[-1])
    if close is None or ma200 is None:return "unknown"
    return "qqq_above_ma200" if close>=ma200 else "qqq_below_ma200"

def outcomes(df,pos,entry,qqq,event_date,expected):
    out={}
    for h in HORIZONS:
        if pos+h>=len(df):out[str(h)]=None;continue
        end=finite(df.iloc[pos+h]["close"])
        if end is None or not entry:out[str(h)]=None;continue
        path=df.iloc[pos+1:pos+h+1]
        lows=[finite(x) for x in path["low"].tolist()]; highs=[finite(x) for x in path["high"].tolist()]
        lows=[x for x in lows if x is not None]; highs=[x for x in highs if x is not None]
        ret=end/entry-1.0; bench=qqq_return(qqq,event_date,h)
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
        if session_distance(index,clusters[-1][-1]["event_date"],row["event_date"])<=CLUSTER_SESSIONS:clusters[-1].append(row)
        else:clusters.append([row])
    return clusters

def avg(values):
    vals=[float(x) for x in values if x is not None and math.isfinite(float(x))]
    return None if not vals else sum(vals)/len(vals)

def summarize_events(events,index):
    clusters=effective_clusters(events,index)
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
    return stats,clusters

def regime_stats(events):
    out={}
    for regime in sorted({e.get("regime","unknown") for e in events}):
        subset=[e for e in events if e.get("regime","unknown")==regime]
        out[regime]={}
        for h in HORIZONS:
            mature=[e["outcomes"].get(str(h)) for e in subset if e["outcomes"].get(str(h))]
            out[regime][str(h)]={
                "n":len(mature),
                "aligned_rate":sum(1 for x in mature if x.get("aligned"))/len(mature) if mature else None,
                "avg_return":avg([x.get("return") for x in mature]),
                "avg_excess_vs_qqq":avg([x.get("excess_vs_qqq") for x in mature]),
            }
    return out

def walk_forward_stats(events):
    """Chronological fixed-rule evaluation. No fitting/threshold selection occurs."""
    rows=sorted(events,key=lambda x:x["event_date"])
    n=len(rows)
    if n<4:return {"mode":"fixed_rule_chronological_no_fitting","folds":[],"note":"insufficient events for temporal folds"}
    cuts=sorted(set([max(1,n//4),max(2,n//2),max(3,(3*n)//4)]))
    folds=[]
    start=0
    for i,end in enumerate(cuts+[n]):
        if end<=start:continue
        fold_rows=rows[start:end]
        horizons={}
        for h in HORIZONS:
            m=[e["outcomes"].get(str(h)) for e in fold_rows if e["outcomes"].get(str(h))]
            horizons[str(h)]={
                "n":len(m),
                "aligned_rate":sum(1 for x in m if x.get("aligned"))/len(m) if m else None,
                "avg_return":avg([x.get("return") for x in m]),
                "avg_excess_vs_qqq":avg([x.get("excess_vs_qqq") for x in m]),
            }
        folds.append({"fold":i+1,"start":fold_rows[0]["event_date"],"end":fold_rows[-1]["event_date"],"horizons":horizons})
        start=end
    return {"mode":"fixed_rule_chronological_no_fitting","folds":folds,"note":"candidate definition is frozen before replay; folds evaluate temporal stability only"}

def replay_candidate(candidate,store,provenance=None):
    syms=list((candidate.get("scope") or {}).get("symbols") or [])
    if candidate.get("reproducibility_status")!="machine_ready_shadow":
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"candidate_not_fully_reproducible","events":[]}
    if len(syms)!=1:return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"single_symbol_scope_required","events":[]}
    expected=direction(candidate)
    if expected is None:return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"direction_not_explicit","events":[]}
    symbol=str(syms[0]).upper(); df=store.get(symbol)
    if df is None or df.empty:
        return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"historical_symbol_missing","data_provenance":(provenance or {}).get(symbol),"events":[]}
    df=normalize_history(df)
    needed=[]
    for cond in candidate.get("conditions") or []:
        series=condition_series(df,cond)
        if series is None:return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"unsupported_replay_condition","events":[]}
        needed.append(series.fillna(False))
    if not needed:return {"candidate_id":candidate.get("candidate_id"),"status":"blocked","reason":"no_replay_conditions","events":[]}
    active=needed[0].copy()
    for s in needed[1:]:active=active & s
    qqq=store.get("QQQ")
    events=[];prev=False
    for i,flag in enumerate(active.tolist()):
        flag=bool(flag)
        if flag and not prev:
            entry=finite(df.iloc[i]["close"])
            if entry:
                day=df.index[i].date().isoformat()
                events.append({
                    "candidate_id":candidate.get("candidate_id"),"symbol":symbol,"event_date":day,
                    "expected_direction":expected,"baseline_close":entry,
                    "regime":event_regime(qqq,day),
                    "evidence_provenance":PROVENANCE,
                    "signal_information_cutoff":day,
                    "outcomes":outcomes(df,i,entry,qqq,day,expected),
                })
        prev=flag
    stats,clusters=summarize_events(events,df.index)
    return {
        "candidate_id":candidate.get("candidate_id"),"status":"replayed","symbol":symbol,
        "method_family":candidate.get("method_family"),"expected_direction":expected,
        "data_provenance":(provenance or {}).get(symbol),
        "raw_events":len(events),"effective_clusters":len(clusters),
        "statistics":stats,"regime_split":regime_stats(events),
        "walk_forward":walk_forward_stats(events),
        "no_lookahead":{
            "signal_inputs":"same_day_or_prior_only",
            "rolling_indicators":"trailing_only",
            "future_bars_used_only_for_outcomes":True,
            "candidate_definition_frozen_before_replay":True,
        },
        "events":events[:80],
    }

def build(registry,store,provenance=None):
    rows=[replay_candidate(c,store,provenance) for c in (registry.get("candidates") or [])]
    return {
        "version":VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"research_shadow_historical_only","evidence_provenance":PROVENANCE,
        "forward_evidence_mixed":False,"automatic_promotion":False,"production_effect":"none",
        "summary":{
            "candidates":len(rows),"replayed":sum(1 for x in rows if x.get("status")=="replayed"),
            "blocked":sum(1 for x in rows if x.get("status")=="blocked"),
            "raw_events":sum(int(x.get("raw_events") or 0) for x in rows),
            "effective_clusters":sum(int(x.get("effective_clusters") or 0) for x in rows),
        },
        "data_provenance":provenance or {},
        "candidates":rows,
        "validation_contract":{
            "horizons":[5,20,60],"baseline":"QQQ same-date return when available",
            "metrics":["raw_n","effective_n","aligned_rate","avg_return","avg_mae","avg_mfe","avg_excess_vs_qqq"],
            "regime":"QQQ above/below trailing MA200",
            "walk_forward":"chronological fixed-rule temporal folds; no parameter fitting",
        },
        "guardrails":[
            "Historical replay is post-candidate-compilation evidence and never Forward evidence.",
            "Only fully reproducible candidate conditions are replayed.",
            "On-demand STOOQ/yfinance history is Research/Shadow-only and cannot become a Production data dependency.",
            "Signals use same-day/past inputs; future bars are used only to calculate later outcomes.",
            "State-entry events are counted; repeated days inside one state are not new events.",
            "Signals within five sessions are clustered for effective-N reporting.",
            "Replay cannot write Promotion Gate, protected rules, positions, sizing or orders.",
        ],
    }

def main():
    registry=load(CANDIDATES,{"candidates":[]})
    store,provenance=resolve_store(registry,read_archive())
    out=build(registry,store,provenance)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["summary"],ensure_ascii=False))

if __name__=="__main__":main()
