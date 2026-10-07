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
from source_history_cache import read_cache  # noqa: E402
from source_intelligence_engine import collect_full_records  # noqa: E402

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

def horizon_stats(df: pd.DataFrame, start, benchmark: pd.DataFrame|None=None, entry_price=None):
    pos=df.index.get_loc(start)
    entry=finite(entry_price)
    if entry is None:
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

def directional_alignment(actions, outcomes, force_direction=None):
    acts=set(actions or [])
    if "sell_put" in acts:
        direction="option_structure"
    elif force_direction:
        direction=force_direction
    elif acts & BULLISH and not acts & BEARISH:
        direction="bullish"
    elif acts & BEARISH and not acts & BULLISH:
        direction="bearish"
    elif acts & BULLISH and acts & BEARISH:
        direction="mixed"
    else:
        direction="neutral"
    result={"direction":direction}
    for h in HORIZONS:
        row=outcomes.get(str(h))
        if not row:
            result[str(h)]=None
            continue
        ret=row.get("return")
        if direction=="option_structure":
            result[str(h)]="not_scored_missing_option_pnl"
        elif ret is None or direction in {"neutral","mixed"}:
            result[str(h)]="not_scored"
        elif direction=="bullish":
            result[str(h)]="aligned" if ret>0 else "not_aligned"
        else:
            result[str(h)]="aligned" if ret<0 else "not_aligned"
    return result

def first_touch_after(df: pd.DataFrame, published: str, level: float):
    start=next_session(df,published)
    if start is None:
        return None
    work=df[df.index>=start]
    hits=work[work["low"]<=level]
    return None if hits.empty else hits.index[0]

def plan_entries(op: dict):
    """Return distinct stock-entry tranches from an author's explicit plan.
    Sell-put strikes are not treated as stock entry prices.
    """
    out=[]
    seen=set()
    for key in ("entry_1","entry_2","entry_below"):
        value=finite(op.get(key))
        if value is None or value in seen:
            continue
        seen.add(value)
        out.append({"kind":key,"level":value})
    return out

def validation_baselines(op: dict, attribution: str, df: pd.DataFrame, published: str):
    entries=plan_entries(op) if attribution=="author_plan" else []
    if entries:
        out=[]
        for item in entries:
            touch=first_touch_after(df,published,item["level"])
            out.append({
                "kind":item["kind"],
                "planned_level":item["level"],
                "triggered":touch is not None,
                "start":touch,
                "entry_price":item["level"],
                "assumption":"explicit plan starts only when the stated stock-entry level is touched",
                "force_direction":"bullish",
            })
        return out
    start=next_session(df,published)
    if start is None:
        return []
    return [{
        "kind":"next_session",
        "planned_level":None,
        "triggered":True,
        "start":start,
        "entry_price":None,
        "assumption":"next trading session open because source date has no reliable intraday timestamp",
        "force_direction":None,
    }]

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

def build(source: dict, store: dict[str,pd.DataFrame], price_provenance: dict|None=None):
    price_provenance=price_provenance or {}
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
                pub_start=next_session(df,rec.get("published_at"))
                if pub_start is None:
                    continue
                for bidx,baseline in enumerate(validation_baselines(op,attribution,df,rec.get("published_at"))):
                    triggered=bool(baseline["triggered"])
                    start=baseline["start"]
                    if triggered:
                        bench=qqq if qqq is not None and start in qqq.index else None
                        entry,outcomes=horizon_stats(df,start,bench,baseline.get("entry_price"))
                        alignment=directional_alignment(op.get("actions"),outcomes,baseline.get("force_direction"))
                        status="mature" if outcomes.get("60") else "developing"
                    else:
                        entry=baseline.get("entry_price")
                        outcomes={str(h):None for h in HORIZONS}
                        alignment={"direction":baseline.get("force_direction") or "neutral", **{str(h):None for h in HORIZONS}}
                        status="not_triggered"
                    event={
                        "event_id":f"{rec.get('id')}:{idx}:{symbol}:{bidx}",
                        "author":rec.get("author"),
                        "title":rec.get("title"),
                        "url":rec.get("url"),
                        "published_at":rec.get("published_at"),
                        "symbol":symbol,
                        "operation":op,
                        "actions":op.get("actions") or [],
                        "attribution":attribution,
                        "attribution_confidence":op.get("attribution_confidence") or "needs_review",
                        "baseline_kind":baseline["kind"],
                        "baseline_assumption":baseline["assumption"],
                        "planned_level":baseline.get("planned_level"),
                        "triggered":triggered,
                        "baseline_date":start.date().isoformat() if start is not None else None,
                        "baseline_price":entry,
                        "price_provenance":{
                            "price_source":(price_provenance.get(symbol) or {}).get("price_source"),
                            "adjustment_basis":(price_provenance.get(symbol) or {}).get("adjustment_basis"),
                            "baseline_source":(price_provenance.get(symbol) or {}).get("price_source"),
                            "horizon_source":(price_provenance.get(symbol) or {}).get("price_source"),
                            "same_source":bool((price_provenance.get(symbol) or {}).get("price_source")),
                        },
                        "outcomes":outcomes,
                        "alignment":alignment,
                        "level_checks":level_checks(op,df,pub_start),
                        "status":status,
                    }
                    events.append(event)

    owned=[e for e in events if e["attribution"] in {"author_action","author_plan"}]
    scored=[e for e in owned if e["triggered"]]

    by_action=defaultdict(list)
    by_author=defaultdict(list)
    for e in scored:
        for a in e["actions"] or (["planned_entry"] if e["baseline_kind"]!="next_session" else ["unspecified"]):
            by_action[a].append(e)
        by_author[e["author"] or "unknown"].append(e)

    def summary(rows):
        out={}
        for h in HORIZONS:
            vals=[x["outcomes"].get(str(h)) for x in rows]
            vals=[x for x in vals if x and x.get("return") is not None]
            aligns=[x["alignment"].get(str(h)) for x in rows]
            aligned=sum(1 for x in aligns if x=="aligned")
            scored_n=sum(1 for x in aligns if x in {"aligned","not_aligned"})
            excess=[x.get("excess_vs_qqq") for x in vals if x.get("excess_vs_qqq") is not None]
            out[str(h)]={
                "n":len(vals),
                "avg_return":sum(x["return"] for x in vals)/len(vals) if vals else None,
                "median_return":float(pd.Series([x["return"] for x in vals]).median()) if vals else None,
                "avg_excess_vs_qqq":sum(excess)/len(excess) if excess else None,
                "alignment_rate":aligned/scored_n if scored_n else None,
            }
        return out

    return {
        "version":2,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "methodology":{
            "executed_action_baseline":"first trading session open strictly after source date when no reliable intraday timestamp exists",
            "planned_entry_baseline":"explicit stock-entry plans begin only on the first later session whose low touches the stated level; each tranche is validated separately",
            "untriggered_plan":"kept as not_triggered and excluded from return/alignment aggregates",
            "horizons":[5,20,60],
            "benchmark":"QQQ when the same baseline session exists",
            "directional_alignment":"descriptive only; explicit staged stock-entry plans are treated bullish after trigger; sell/trim/clear bearish",
            "sell_put_limit":"without option premium/expiry/IV, Sell Put P&L and alignment are not scored; strike-touch remains descriptive",
            "attribution_limit":"third-party examples are excluded; unconfirmed source context is visible but excluded from aggregate method memory",
        },
        "counts":{
            "events":len(events),
            "author_owned":len(owned),
            "unconfirmed":sum(1 for x in events if x["attribution"] not in {"author_action","author_plan"}),
            "triggered_author_owned":sum(1 for x in owned if x["triggered"]),
            "untriggered_plans":sum(1 for x in owned if x["status"]=="not_triggered"),
            "mature60":sum(1 for x in owned if x["outcomes"].get("60")),
            "developing":sum(1 for x in owned if x["triggered"] and not x["outcomes"].get("60")),
            "symbols":len(set(x["symbol"] for x in events)),
        },
        "missing_history":dict(missing),
        "by_action":{k:summary(v) for k,v in sorted(by_action.items())},
        "by_author":{k:summary(v) for k,v in sorted(by_author.items())},
        "events":sorted(events,key=lambda x:(x.get("published_at") or "",x["symbol"],x["baseline_kind"]),reverse=True),
        "guardrails":[
            "External-source outcomes are descriptive evidence, not rankings or automatic trade rules.",
            "Quoted third-party examples are excluded from author-level outcome aggregates.",
            "Unconfirmed attribution is excluded from aggregate method memory.",
            "Planned entries are scored only after the exact stated price level is actually touched.",
            "Sell Put is not assigned a synthetic P&L when premium/expiry/IV are missing.",
            "No learning result changes production thresholds without separate validation.",
        ],
    }

def main():
    source=load(SOURCE,{"operation_cases":[]})
    try:
        full=collect_full_records()
        source=dict(source)
        source["operation_cases"]=[r for r in full if r.get("operations") or r.get("actions")]
        source["full_stream_learning"]=True
    except Exception:
        pass
    core=read_archive()
    fallback=read_cache()
    store={**fallback, **core}  # Whole-symbol precedence only; never splice sources inside one event.
    provenance={}
    for sym in fallback:
        provenance[sym]={
            "price_source":"yfinance_validation_cache",
            "adjustment_basis":"yfinance_auto_adjust_false_native_ohlc",
        }
    for sym in core:
        provenance[sym]={
            "price_source":"stooq_archive",
            "adjustment_basis":"stooq_archive_native_series",
        }
    result=build(source,store,provenance)
    result["history_sources"]={
        "core_stooq_symbols":len(core),
        "source_validation_cache_symbols":len(fallback),
        "principle":"STOOQ core wins at whole-symbol level; baseline and every horizon for an event use the same target-symbol source. yfinance remains validation-only fallback."
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result["counts"],ensure_ascii=False))
    if result["missing_history"]:
        print("missing history:",json.dumps(result["missing_history"],ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
