#!/usr/bin/env python3
"""Validate external-source operations against local point-in-time market history.

This engine does not decide whether an author is "right" or "wrong".
It records what happened after a sourced operation/plan:
- next-session baseline
- 5/20/60 trading-day return, MAE/MFE
- excess return vs QQQ when available
- whether stated entry/target/exit/put-strike levels were touched
- directional alignment for clearly bullish/bearish actions

No external-source result can directly modify production trading thresholds.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "data" / "source_intelligence.json"
OUT = ROOT / "docs" / "research" / "source_outcome_validation.json"
HORIZONS = (5, 20, 60)

sys.path.insert(0, str(ROOT / "scripts"))
from local_history_agent import read_archive  # noqa: E402

BULLISH = {"buy", "add", "hold", "sell_put"}
BEARISH = {"sell", "trim", "trim_half", "clear"}
NEUTRAL = {"no_add", "no_direct_stock_buy"}

def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def next_session(df: pd.DataFrame, published: str):
    try:
        d=pd.Timestamp(str(published)[:10])
    except Exception:
        return None
    future=df[df.index > d]
    if future.empty:
        return None
    return future.index[0]

def horizon_stats(df: pd.DataFrame, start, benchmark: pd.DataFrame|None=None):
    pos=df.index.get_loc(start)
    entry=float(df.loc[start,"open"])
    out={}
    for h in HORIZONS:
        if pos+h >= len(df):
            out[str(h)]=None
            continue
        path=df.iloc[pos:pos+h+1]
        end=float(path.iloc[-1]["close"])
        mae=float(path["low"].min()/entry-1.0)
        mfe=float(path["high"].max()/entry-1.0)
        row={
            "date":path.index[-1].date().isoformat(),
            "return":end/entry-1.0,
            "mae":mae,
            "mfe":mfe,
        }
        if benchmark is not None and start in benchmark.index:
            bpos=benchmark.index.get_loc(start)
            if isinstance(bpos,slice): bpos=bpos.start
            if isinstance(bpos,int) and bpos+h < len(benchmark):
                bentry=float(benchmark.loc[start,"open"])
                bend=float(benchmark.iloc[bpos+h]["close"])
                row["benchmark_return"]=bend/bentry-1.0
                row["excess_vs_qqq"]=row["return"]-row["benchmark_return"]
        out[str(h)]=row
    return entry,out

def touched(df: pd.DataFrame, start, level: float, direction: str, horizon=60):
    pos=df.index.get_loc(start)
    end=min(len(df),pos+horizon+1)
    work=df.iloc[pos:end]
    if work.empty:return None
    if direction=="down":
        hits=work[work["low"]<=level]
    else:
        hits=work[work["high"]>=level]
    if hits.empty:
        return {"touched":False,"within_sessions":horizon}
    idx=hits.index[0]
    return {"touched":True,"date":idx.date().isoformat(),"within_sessions":horizon}

def directional_alignment(actions, outcomes):
    acts=set(actions or [])
    direction="neutral"
    if acts & BULLISH and not acts & BEARISH: direction="bullish"
    elif acts & BEARISH and not acts & BULLISH: direction="bearish"
    elif acts & BULLISH and acts & BEARISH: direction="mixed"
    result={"direction":direction}
    for h in HORIZONS:
        row=outcomes.get(str(h))
        if not row:
            result[str(h)]=None
            continue
        ret=row.get("return")
        if ret is None or direction in {"neutral","mixed"}:
            result[str(h)]="not_scored"
        elif direction=="bullish":
            result[str(h)]="aligned" if ret>0 else "not_aligned"
        else:
            result[str(h)]="aligned" if ret<0 else "not_aligned"
    return result

def level_checks(op, df, start):
    checks={}
    for key in ("entry_1","entry_2","entry_below","sell_put_strike"):
        level=finite(op.get(key))
        if level is not None:
            checks[key]={"level":level,"touch20":touched(df,start,level,"down",20),"touch60":touched(df,start,level,"down",60)}
    level=finite(op.get("exit_line"))
    if level is not None:
        checks["exit_line"]={"level":level,"touch20":touched(df,start,level,"up",20),"touch60":touched(df,start,level,"up",60)}
    trg=op.get("target_range")
    if isinstance(trg,list) and len(trg)==2:
        low,high=finite(trg[0]),finite(trg[1])
        if low is not None:
            checks["target_low"]={"level":low,"touch20":touched(df,start,low,"up",20),"touch60":touched(df,start,low,"up",60)}
        if high is not None:
            checks["target_high"]={"level":high,"touch20":touched(df,start,high,"up",20),"touch60":touched(df,start,high,"up",60)}
    return checks

def build(source: dict, store: dict[str,pd.DataFrame]):
    qqq=store.get("QQQ")
    events=[]
    missing=Counter()
    for rec in source.get("operation_cases") or []:
        for idx,op in enumerate(rec.get("operations") or []):
            attribution=op.get("attribution") or "unconfirmed_author_context"
            if attribution=="third_party_example":
                continue
            symbols=op.get("symbols") or rec.get("symbols") or []
            for symbol in symbols:
                df=store.get(symbol)
                if df is None or df.empty:
                    missing[symbol]+=1
                    continue
                start=next_session(df,rec.get("published_at"))
                if start is None:
                    continue
                bench=None
                if qqq is not None and start in qqq.index:
                    bench=qqq
                entry,outcomes=horizon_stats(df,start,bench)
                event={
                    "event_id":f"{rec.get('id')}:{idx}:{symbol}",
                    "author":rec.get("author"),
                    "title":rec.get("title"),
                    "url":rec.get("url"),
                    "published_at":rec.get("published_at"),
                    "symbol":symbol,
                    "operation":op,
                    "actions":op.get("actions") or [],
                    "attribution":attribution,
                    "attribution_confidence":op.get("attribution_confidence") or "needs_review",
                    "baseline_assumption":"next trading session open because source date has no reliable intraday timestamp",
                    "baseline_date":start.date().isoformat(),
                    "baseline_price":entry,
                    "outcomes":outcomes,
                    "alignment":directional_alignment(op.get("actions"),outcomes),
                    "level_checks":level_checks(op,df,start),
                    "status":"mature" if outcomes.get("60") else "developing",
                }
                events.append(event)

    by_action=defaultdict(list)
    by_author=defaultdict(list)
    for e in events:
        for a in e["actions"] or ["unspecified"]:
            by_action[a].append(e)
        by_author[e["author"] or "unknown"].append(e)

    def summary(rows):
        out={}
        for h in HORIZONS:
            vals=[x["outcomes"].get(str(h)) for x in rows]
            vals=[x for x in vals if x and x.get("return") is not None]
            aligns=[x["alignment"].get(str(h)) for x in rows]
            aligned=sum(1 for x in aligns if x=="aligned")
            scored=sum(1 for x in aligns if x in {"aligned","not_aligned"})
            out[str(h)]={
                "n":len(vals),
                "avg_return":sum(x["return"] for x in vals)/len(vals) if vals else None,
                "median_return":float(pd.Series([x["return"] for x in vals]).median()) if vals else None,
                "avg_excess_vs_qqq":sum(x.get("excess_vs_qqq",0) for x in vals if x.get("excess_vs_qqq") is not None)/sum(1 for x in vals if x.get("excess_vs_qqq") is not None) if any(x.get("excess_vs_qqq") is not None for x in vals) else None,
                "alignment_rate":aligned/scored if scored else None,
            }
        return out

    return {
        "version":1,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "methodology":{
            "baseline":"first trading session open strictly after source date",
            "horizons":[5,20,60],
            "benchmark":"QQQ when the same baseline session exists",
            "directional_alignment":"descriptive only; buy/add/hold/sell_put are treated bullish, sell/trim/clear bearish",
            "sell_put_limit":"premium/IV/expiry are often unavailable; strike touch is tracked but P&L is not inferred",
            "attribution_limit":"until quote-vs-author attribution is confirmed, operation results remain research candidates",
        },
        "counts":{
            "events":len(events),
            "author_owned":sum(1 for x in events if x["attribution"] in {"author_action","author_plan"}),
            "unconfirmed":sum(1 for x in events if x["attribution"] not in {"author_action","author_plan"}),
            "mature60":sum(1 for x in events if x["outcomes"].get("60")),
            "developing":sum(1 for x in events if not x["outcomes"].get("60")),
            "symbols":len(set(x["symbol"] for x in events)),
        },
        "missing_history":dict(missing),
        "by_action":{k:summary(v) for k,v in sorted(by_action.items())},
        "by_author":{k:summary(v) for k,v in sorted(by_author.items())},
        "events":sorted(events,key=lambda x:(x.get("published_at") or "",x["symbol"]),reverse=True),
        "guardrails":[
            "External-source outcomes are descriptive evidence, not rankings or automatic trade rules.",
            "Quoted third-party examples must not be learned as the source author's own trades.",
            "No learning result changes production thresholds without separate validation.",
            "Missing timestamps, option premiums, expiries or position size are never invented.",
        ],
    }

def main():
    source=load(SOURCE,{"operation_cases":[]})
    store=read_archive()
    result=build(source,store)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result["counts"],ensure_ascii=False))
    if result["missing_history"]:
        print("missing history:",json.dumps(result["missing_history"],ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
