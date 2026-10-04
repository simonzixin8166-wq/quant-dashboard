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


def direct_methods(record: dict, event: dict):
    """Conservative event-level method attribution.

    Article topics are context only. Direct method attribution may also come
    from explicit operation semantics when the method is unambiguous from the
    event itself. This prevents article-topic misses from permanently blocking
    valid method learning, while avoiding inference for broad concepts such as
    valuation, risk management or long-term discipline.
    """
    op=event.get("operation") or {}
    actions=set(event.get("actions") or op.get("actions") or [])
    title=(record.get("title") or event.get("title") or "").lower()
    excerpt=(record.get("excerpt") or "").lower()
    text=title+"\n"+excerpt
    out=set()

    # Explicit option structure.
    if "sell_put" in actions or op.get("sell_put_strike") is not None:
        out.add("Sell Put")

    # Explicit position-size / add-reduce actions are themselves direct evidence
    # of the position-management method category.
    sizing_actions={"buy","add","trim","trim_half","sell","clear","planned_buy","planned_sell"}
    has_plan_level=any(op.get(k) is not None for k in ("entry_1","entry_2","entry_below","exit_line","target_range"))
    if actions & sizing_actions or has_plan_level:
        out.add("仓位与加减仓")

    # LEAPS requires explicit structure text/field, never article topic alone.
    explicit_leaps = (
        "leap" in text
        or any("leap" in str(x).lower() for x in actions)
        or "leap" in str(op.get("strategy") or "").lower()
        or "leap" in str(op.get("option_type") or "").lower()
    )
    if explicit_leaps:
        out.add("LEAPS")

    # Trend confirmation requires an event-level trigger/condition.
    cond=" ".join(str(x).lower() for x in (op.get("conditions") or []))
    if any(k in cond for k in ("trend","breakout","ma20","ma21","ma50","tcds","supertrend")):
        out.add("趋势确认")
    return out


def evidence_state(direct_events):
    """Automatic method evidence maturity, research-only.

    Uses only direct-attribution outcomes. Small samples stay early/developing.
    Support/challenge labels require >=8 mature 20-session direct events.
    """
    n=len(direct_events)
    mature20=[e for e in direct_events if (e.get("outcomes") or {}).get("20")]
    mature60=[e for e in direct_events if (e.get("outcomes") or {}).get("60")]
    if n==0:
        return {"state":"context_only","basis_horizon":None,"mature_n":0,"alignment_rate":None}
    if len(mature20)<3:
        return {"state":"direct_early","basis_horizon":5 if any((e.get("outcomes") or {}).get("5") for e in direct_events) else None,"mature_n":len(mature20),"alignment_rate":None}
    if len(mature20)<8:
        return {"state":"direct_developing","basis_horizon":20,"mature_n":len(mature20),"alignment_rate":None}
    basis="60" if len(mature60)>=5 else "20"
    rows=mature60 if basis=="60" else mature20
    aligns=[e.get("alignment",{}).get(basis) for e in rows if e.get("alignment",{}).get(basis) in {"aligned","not_aligned"}]
    rate=(sum(1 for x in aligns if x=="aligned")/len(aligns)) if aligns else None
    if rate is None:
        state="direct_developing"
    elif rate>=0.60:
        state="outcome_supportive"
    elif rate<=0.40:
        state="outcome_challenging"
    else:
        state="outcome_mixed"
    return {"state":state,"basis_horizon":int(basis),"mature_n":len(rows),"alignment_rate":rate}


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
    context_buckets=defaultdict(list)
    direct_buckets=defaultdict(list)
    context_states=defaultdict(Counter)
    direct_states=defaultdict(Counter)
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
        context_methods=sorted(set(r.get("topics") or []) & METHOD_TOPICS)
        direct=sorted(direct_methods(r,e))
        if not context_methods and not direct:
            continue
        ctx=market_context(histories,e.get("baseline_date"))
        item=dict(e)
        item["_context_methods"]=context_methods
        item["_direct_methods"]=direct
        item["_context"]=ctx
        joined.append(item)
        for method in context_methods:
            context_buckets[method].append(item)
            context_states[method][ctx.get("state") or "unknown"]+=1
        for method in direct:
            direct_buckets[method].append(item)
            direct_states[method][ctx.get("state") or "unknown"]+=1

    methods=[]
    for method in sorted(set(source_occurrences)|set(context_buckets)|set(direct_buckets)):
        context_evs=context_buckets.get(method,[])
        direct_evs=direct_buckets.get(method,[])
        mature60=sum(1 for e in direct_evs if e.get("outcomes",{}).get("60"))
        failures=[]
        for e in direct_evs:
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
        maturity=evidence_state(direct_evs)
        methods.append({
            "method":method,
            "source_occurrences":source_occurrences.get(method,0),
            "authors":sorted(source_authors.get(method,set())),
            "direct_validated_events":len(direct_evs),
            "context_validated_events":len(context_evs),
            "mature60_direct":mature60,
            "performance_basis":"direct_event_attribution" if direct_evs else "context_only_no_method_performance",
            "performance":summarize_events(direct_evs) if direct_evs else None,
            "context_performance":summarize_events(context_evs),
            "market_context_counts":dict(direct_states.get(method,{})),
            "context_market_counts":dict(context_states.get(method,{})),
            "failure_examples":failures[:12],
            "status":maturity["state"],
            "evidence_maturity":maturity,
            "interpretation_guardrail":"performance 仅统计可直接归因到该方法的事件；context_performance 只描述同篇文章中的同期结果，不能视为方法有效性证明。",
        })

    return {
        "version":"6.13.1",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "counts":{
            "methods":len(methods),
            "source_records":source.get("counts",{}).get("records",0),
            "eligible_triggered_events":len(joined),
            "direct_method_links":sum(len(e.get("_direct_methods") or []) for e in joined),
            "mature60_eligible_events":sum(1 for e in joined if e.get("outcomes",{}).get("60")),
        },
        "methodology":{
            "eligible_events":"author_action / author_plan + triggered only",
            "attribution_layers":"article topics are context; direct performance may also come from explicit unambiguous operation semantics",
            "excluded":"third-party examples, unconfirmed attribution, untriggered plans",
            "horizons":[5,20,60],
            "risk_metrics":"MAE/MFE measured from validated baseline price",
            "benchmark":"QQQ excess return when available",
            "market_context":"QQQ position vs 20/50-day moving averages plus 60-day drawdown and 20-day realized volatility",
            "causality":"none claimed",
            "evidence_state_policy":"context_only -> direct_early -> direct_developing -> outcome_supportive/mixed/challenging; supportive/challenging requires >=8 mature 20-session direct events",
        },
        "methods":methods,
        "guardrails":[
            "Method Memory learns from outcomes; it does not copy an author's conclusion into MyAlpha.",
            "Article-level method tags never automatically convert every operation in that article into method performance.",
            "Explicit sell-put, LEAPS, position-adjustment and technical-condition semantics may create direct method links even when article topics miss the category.",
            "Small direct samples are displayed as evidence_building rather than treated as stable edge.",
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
