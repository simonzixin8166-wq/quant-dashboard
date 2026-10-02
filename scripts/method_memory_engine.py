#!/usr/bin/env python3
"""MyAlpha V5.9 Method Memory.

Turns sourced research records + independently validated outcomes into an
auditable method-level memory. External authors remain evidence sources, not
trading authorities. Only author-owned, triggered validation events enter
performance aggregates.

Outputs:
- method occurrence counts
- 5/20/60 session return / MAE / MFE / QQQ excess statistics
- market-context buckets at the event baseline
- failure / non-alignment examples for review
"""
from __future__ import annotations

import json, math, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "data" / "source_intelligence.json"
VALIDATION = ROOT / "docs" / "research" / "source_outcome_validation.json"
EVIDENCE = ROOT / "docs" / "research" / "evidence_attribution.json"
OUT = ROOT / "docs" / "research" / "method_memory.json"
HORIZONS = ("5","20","60")
METHOD_TOPICS = {
    "Sell Put","LEAPS","风险管理","失败复盘","长期持有纪律",
    "仓位与加减仓","估值与价格","趋势确认","AI研究方法",
}

sys.path.insert(0, str(ROOT / "scripts"))
from local_history_agent import read_archive  # noqa: E402
from source_history_cache import read_cache  # noqa: E402


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


def median(values):
    vals=sorted(x for x in (finite(v) for v in values) if x is not None)
    if not vals:return None
    n=len(vals)
    return vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2


def avg(values):
    vals=[x for x in (finite(v) for v in values) if x is not None]
    return sum(vals)/len(vals) if vals else None


def record_index(source: dict):
    by_url={}
    for r in source.get("records") or []:
        url=str(r.get("url") or "")
        if url:
            by_url[url]=r
    return by_url


def merge_history():
    local=read_archive()
    cache=read_cache()
    for sym,df in cache.items():
        if sym not in local or len(df) > len(local[sym]):
            local[sym]=df
    return local


def market_context(histories: dict, baseline_date: str):
    """Describe the broad QQQ environment without claiming causality."""
    q=histories.get("QQQ")
    if q is None or q.empty or not baseline_date:
        return {"state":"unknown"}
    try:
        d=pd.Timestamp(str(baseline_date)[:10])
    except Exception:
        return {"state":"unknown"}
    work=q[q.index <= d].copy()
    if work.empty:
        return {"state":"unknown"}
    close=work["close"].astype(float)
    px=float(close.iloc[-1])
    ma20=float(close.tail(20).mean()) if len(close)>=20 else None
    ma50=float(close.tail(50).mean()) if len(close)>=50 else None
    hi60=float(close.tail(60).max()) if len(close)>=20 else None
    ret=close.pct_change().dropna().tail(20)
    rv20=float(ret.std()*(252**0.5)) if len(ret)>=10 else None
    dd60=px/hi60-1 if hi60 else None
    if ma20 is None:
        state="insufficient"
    elif px>=ma20 and (ma50 is None or px>=ma50):
        state="trend_positive"
    elif ma50 is not None and px<ma20 and px<ma50:
        state="trend_weak"
    else:
        state="mixed"
    return {
        "state":state,
        "qqq_close":px,
        "above_ma20": None if ma20 is None else px>=ma20,
        "above_ma50": None if ma50 is None else px>=ma50,
        "qqq_drawdown_60":dd60,
        "qqq_realized_vol_20":rv20,
    }


def summarize_events(events):
    out={}
    for h in HORIZONS:
        rows=[e["outcomes"].get(h) for e in events if isinstance(e.get("outcomes"),dict) and e["outcomes"].get(h)]
        aligns=[e.get("alignment",{}).get(h) for e in events if e.get("alignment",{}).get(h) in {"aligned","not_aligned"}]
        out[h]={
            "n":len(rows),
            "avg_return":avg([r.get("return") for r in rows]),
            "median_return":median([r.get("return") for r in rows]),
            "avg_mae":avg([r.get("mae") for r in rows]),
            "median_mae":median([r.get("mae") for r in rows]),
            "avg_mfe":avg([r.get("mfe") for r in rows]),
            "median_mfe":median([r.get("mfe") for r in rows]),
            "avg_excess_vs_qqq":avg([r.get("excess_vs_qqq") for r in rows]),
            "alignment_rate": (sum(1 for x in aligns if x=="aligned")/len(aligns)) if aligns else None,
        }
    return out


def build(source: dict, validation: dict, histories: dict|None=None, evidence: dict|None=None):
    histories=histories or {}
    evidence=evidence or {}
    by_url=record_index(source)
    buckets=defaultdict(list)
    contexts=defaultdict(Counter)
    source_occurrences=Counter()
    source_authors=defaultdict(set)

    for r in source.get("records") or []:
        for method in (set(r.get("topics") or []) & METHOD_TOPICS):
            source_occurrences[method]+=1
            source_authors[method].add(r.get("author") or "未知作者")

    joined=[]
    for e in validation.get("events") or []:
        if e.get("attribution") not in {"author_action","author_plan"}:
            continue
        if not e.get("triggered"):
            continue
        r=by_url.get(str(e.get("url") or ""))
        if not r:
            continue
        methods=sorted(set(r.get("topics") or []) & METHOD_TOPICS)
        if not methods:
            continue
        ctx=market_context(histories,e.get("baseline_date"))
        item=dict(e)
        item["_methods"]=methods
        item["_context"]=ctx
        joined.append(item)
        for method in methods:
            buckets[method].append(item)
            contexts[method][ctx.get("state") or "unknown"]+=1

    methods=[]
    for method in sorted(set(source_occurrences)|set(buckets)):
        evs=buckets.get(method,[])
        mature60=sum(1 for e in evs if e.get("outcomes",{}).get("60"))
        failures=[]
        for e in evs:
            h="60" if e.get("outcomes",{}).get("60") else ("20" if e.get("outcomes",{}).get("20") else "5")
            outcome=e.get("outcomes",{}).get(h)
            align=e.get("alignment",{}).get(h)
            if outcome and (align=="not_aligned" or finite(outcome.get("return")) is not None and outcome.get("return")<0):
                failures.append({
                    "event_id":e.get("event_id"),"author":e.get("author"),"symbol":e.get("symbol"),
                    "title":e.get("title"),"url":e.get("url"),"baseline_date":e.get("baseline_date"),
                    "horizon":int(h),"return":outcome.get("return"),"mae":outcome.get("mae"),
                    "mfe":outcome.get("mfe"),"alignment":align,"market_context":e.get("_context"),
                })
        methods.append({
            "method":method,
            "source_occurrences":source_occurrences.get(method,0),
            "authors":sorted(source_authors.get(method,set())),
            "validated_triggered_events":len(evs),
            "mature60":mature60,
            "performance":summarize_events(evs),
            "market_context_counts":dict(contexts.get(method,{})),
            "failure_examples":failures[:12],
            "status":"evidence_building" if len(evs)<8 else "research_memory",
            "interpretation_guardrail":"描述历史样本，不构成方法有效性证明或交易信号；样本选择、作者行为和市场环境可能存在偏差。",
        })

    return {
        "version":"5.9.1",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "counts":{
            "methods":len(methods),
            "source_records":source.get("counts",{}).get("records",0),
            "validated_triggered_events":len(joined),
            "mature60_events":sum(1 for e in joined if e.get("outcomes",{}).get("60")),
        },
        "methodology":{
            "eligible_events":"author_action / author_plan + triggered only",
            "excluded":"third-party examples, unconfirmed attribution, untriggered plans",
            "horizons":[5,20,60],
            "risk_metrics":"MAE/MFE measured from validated baseline price",
            "benchmark":"QQQ excess return when available",
            "market_context":"QQQ position vs 20/50-day moving averages plus 60-day drawdown and 20-day realized volatility",
            "causality":"none claimed",
        },
        "methods":methods,
        "guardrails":[
            "Method Memory learns from outcomes; it does not copy an author's conclusion into MyAlpha.",
            "Small samples are displayed as evidence_building rather than treated as stable edge.",
            "Failure examples are counterexamples for review, not labels that an author or method is generally wrong.",
            "No Method Memory statistic may directly change production trading thresholds without a separate validated policy step.",
        ],
    }


def main():
    source=load(SOURCE,{})
    validation=load(VALIDATION,{})
    evidence=load(EVIDENCE,{})
    result=build(source,validation,merge_history(),evidence)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result["counts"],ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
