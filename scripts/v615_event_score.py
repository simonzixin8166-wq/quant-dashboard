#!/usr/bin/env python3
"""V6.15.2 EventScore compatibility layer.

This module adapts existing Source Outcome events to one versioned score format.
It does not replace the legacy engines yet.
"""
from __future__ import annotations
import hashlib, json, math, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
VALIDATION=ROOT/"docs"/"research"/"source_outcome_validation.json"
REGISTRY=ROOT/"research"/"registry"/"rules.json"
OUT=ROOT/"research"/"events"/"event_scores_v1.json"
COMPARE=ROOT/"research"/"audit"/"v615_eventscore_comparison.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
CACHE_AUDIT=ROOT/"research"/"audit"/"v615_cache_only_stooq_coverage.json"

sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import load_spec,direction_adjusted_return
from local_history_agent import read_archive
from source_history_cache import read_cache

VERSION="6.15.8a"
HORIZONS=(5,20,60)

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def frame_hash(df):
    if df is None or df.empty:return None
    cols=[c for c in ("open","high","low","close") if c in df.columns]
    payload=df[cols].copy().sort_index().to_csv(date_format="%Y-%m-%d",float_format="%.10g")
    return hashlib.sha256(payload.encode()).hexdigest()

def reconcile_history(stooq,cache,tolerance=0.005):
    """STOOQ is canonical; cache can fill dates absent from STOOQ only."""
    if stooq is None or stooq.empty:
        if cache is None or cache.empty:
            return None,{"status":"missing","source":"none","price_series_hash":None}
        # Without canonical STOOQ this is context-only, never scoreable.
        c=cache.copy().sort_index()
        return c,{"status":"cache_only_unscored","source":"cache","price_series_hash":frame_hash(c)}
    base=stooq.copy().sort_index()
    status="ok"
    overlap=[]
    if cache is not None and not cache.empty:
        common=base.index.intersection(cache.index)
        for dt in common:
            a=float(base.loc[dt,"close"]); b=float(cache.loc[dt,"close"])
            if a and abs(a-b)/abs(a)>tolerance:
                overlap.append({"date":str(dt)[:10],"stooq":a,"cache":b})
        if overlap:
            status="conflict"
        else:
            gap=cache.loc[~cache.index.isin(base.index)]
            if not gap.empty:
                base=pd.concat([base,gap]).sort_index()
    return base,{
        "status":status,
        "source":"stooq_archive+cache_gap_fill" if cache is not None and not cache.empty else "stooq_archive",
        "price_series_hash":frame_hash(base),
        "overlap_conflicts":overlap[:10],
    }

def parse_event_identity(event):
    raw=str(event.get("event_id") or "")
    parts=raw.rsplit(":",3)
    if len(parts)==4:
        sid,op_idx,symbol,baseline_idx=parts
        try:op_idx=int(op_idx)
        except Exception:op_idx=None
        return sid,op_idx,symbol,baseline_idx
    return None,None,event.get("symbol"),None

def entry_type(event):
    kind=str(event.get("baseline_kind") or "")
    op=event.get("operation") or {}
    conditions=" ".join(str(x).lower() for x in (op.get("conditions") or []))
    if kind=="next_session":return "next_session"
    if any(k in conditions for k in ("breakout","突破","站上","above resistance","break above")):
        return "breakout"
    if kind=="entry_below":
        return "conditional"
    if kind in {"entry_1","entry_2"}:
        if any(k in conditions for k in ("pullback","回调","回踩","跌到","below","limit")):
            return "pullback_limit"
        return "unknown"
    return "unknown"

def direction_from_event(event):
    d=(event.get("alignment") or {}).get("direction")
    return d if d in {"bullish","bearish"} else ("option_structure" if d=="option_structure" else "unknown")

def direction_adjusted_excursions(direction,mae,mfe):
    if mae is None or mfe is None:return None,None
    if direction=="bullish":
        return float(mae),float(mfe)
    if direction=="bearish":
        # For a bearish thesis, price rises are adverse and price falls favorable.
        return -float(mfe),-float(mae)
    return None,None

def historical_unconditional_metrics(df,baseline_date,horizon,direction,max_samples=252):
    """Prior-only unconditional same-symbol baseline for return and adverse excursion."""
    if df is None or df.empty or not baseline_date:return None
    try:d=pd.Timestamp(str(baseline_date)[:10])
    except Exception:return None
    work=df[df.index<d].copy()
    if len(work)<=horizon+1:return None
    returns=[]; maes=[]
    for i in range(max(0,len(work)-max_samples-horizon),len(work)-horizon):
        try:
            entry=float(work.iloc[i]["open"])
            path=work.iloc[i:i+horizon+1]
            end=float(path.iloc[-1]["close"])
            raw=end/entry-1.0
            raw_mae=float(path["low"].min()/entry-1.0)
            raw_mfe=float(path["high"].max()/entry-1.0)
            adj=direction_adjusted_return(direction,raw)
            adj_mae,_=direction_adjusted_excursions(direction,raw_mae,raw_mfe)
            if adj is not None:returns.append(adj)
            if adj_mae is not None:maes.append(adj_mae)
        except Exception:
            continue
    if not returns:return None
    return {
        "n":len(returns),
        "direction_adjusted_return":sum(returns)/len(returns),
        "direction_adjusted_mae":sum(maes)/len(maes) if maes else None,
    }

def registry_map(registry):
    out={}
    for m in registry.get("legacy_mapping") or []:
        out[(str(m.get("source_id")),m.get("operation_index"))]=m.get("rule_id")
    return out

def source_provenance_map(store):
    out={}
    for row in store.get("records") or []:
        rec=row.get("record") or {}
        sid=rec.get("id") or row.get("source_key")
        if sid is None:continue
        out[str(sid)]={
            "first_fetched_at":row.get("first_fetched_at"),
            "ingest_type":row.get("ingest_type"),
            "published_at_semantics":row.get("published_at_semantics"),
            "timestamp_confidence":row.get("timestamp_confidence"),
            "snapshot_hash":row.get("snapshot_hash"),
        }
    return out

def point_in_time_status(prov,baseline_date):
    first=(prov or {}).get("first_fetched_at")
    if not first or not baseline_date:
        return "unknown"
    try:
        first_day=pd.Timestamp(str(first)[:10])
        baseline=pd.Timestamp(str(baseline_date)[:10])
        return "eligible" if baseline>=first_day else "historical_pre_ingest"
    except Exception:
        return "unknown"

def exclusion_reasons(rid,triggered,direction,entry_type,data_status,point_status):
    reasons=[]
    if not rid:reasons.append("missing_rule_id")
    if not triggered:reasons.append("not_triggered")
    if direction=="option_structure":reasons.append("missing_real_option_pnl")
    elif direction not in {"bullish","bearish"}:reasons.append("unsupported_direction")
    if entry_type=="unknown":reasons.append("unknown_entry_semantics")
    if data_status=="conflict":reasons.append("price_source_conflict")
    elif data_status=="cache_only_unscored":reasons.append("cache_only_unscored")
    elif data_status!="ok":reasons.append("missing_price_data")
    if point_status=="historical_pre_ingest":reasons.append("non_point_in_time_source")
    elif point_status=="unknown":reasons.append("timestamp_provenance_unknown")
    return reasons

PRIMARY_PRECEDENCE=(
    "missing_rule_id",
    "missing_real_option_pnl",
    "unsupported_direction",
    "unknown_entry_semantics",
    "not_triggered",
    "price_source_conflict",
    "cache_only_unscored",
    "missing_price_data",
    "non_point_in_time_source",
    "timestamp_provenance_unknown",
)

def choose_primary(reasons):
    for key in PRIMARY_PRECEDENCE:
        if key in reasons:return key
    return None

def adapt(validation,registry,histories=None,spec=None,source_store=None):
    spec=spec or load_spec()
    mapping=registry_map(registry)
    histories=histories or {}
    provenance=source_provenance_map(source_store or {})
    rows=[]
    primary_counts=Counter()
    for ev in validation.get("events") or []:
        sid,op_idx,symbol,_=parse_event_identity(ev)
        rid=mapping.get((str(sid),op_idx))
        et=entry_type(ev)
        direction=direction_from_event(ev)
        hmeta=histories.get(symbol,{}).get("meta") or {}
        prov=provenance.get(str(sid)) or {}
        pit=point_in_time_status(prov,ev.get("baseline_date"))
        reasons=exclusion_reasons(rid,bool(ev.get("triggered")),direction,et,hmeta.get("status"),pit)
        primary=choose_primary(reasons)
        secondary=[x for x in reasons if x!=primary]
        scoreable=primary is None
        if primary:primary_counts[primary]+=1
        scores={}
        for h in HORIZONS:
            old=(ev.get("outcomes") or {}).get(str(h))
            if not old:
                scores[str(h)]=None;continue
            raw=old.get("return")
            adj=direction_adjusted_return(direction,raw)
            hist=histories.get(symbol,{}).get("df")
            raw_mae=old.get("mae");raw_mfe=old.get("mfe")
            adj_mae,adj_mfe=direction_adjusted_excursions(direction,raw_mae,raw_mfe)
            baseline=historical_unconditional_metrics(hist,ev.get("baseline_date"),h,direction)
            uncond_adj=(baseline or {}).get("direction_adjusted_return")
            lift=None if adj is None or uncond_adj is None else adj-uncond_adj
            scores[str(h)]={
                "raw_return":raw,
                "direction_adjusted_return":adj,
                "benchmark_return":old.get("benchmark_return"),
                "excess_vs_qqq":old.get("excess_vs_qqq"),
                "unconditional_baseline_direction_adjusted_return":uncond_adj,
                "unconditional_baseline_direction_adjusted_mae":(baseline or {}).get("direction_adjusted_mae"),
                "unconditional_baseline_n":(baseline or {}).get("n"),
                "unconditional_lift":lift,
                "mae":raw_mae,
                "mfe":raw_mfe,
                "direction_adjusted_mae":adj_mae,
                "direction_adjusted_mfe":adj_mfe,
                "legacy_alignment":(ev.get("alignment") or {}).get(str(h)),
            }
        rows.append({
            "event_id":ev.get("event_id"),
            "rule_id":rid,
            "legacy_source_id":sid,
            "legacy_operation_index":op_idx,
            "spec_version":spec.get("spec_version"),
            "author":ev.get("author"),
            "symbol":symbol,
            "published_at":ev.get("published_at"),
            "baseline_date":ev.get("baseline_date"),
            "entry_type":et,
            "direction":direction,
            "triggered":bool(ev.get("triggered")),
            "scoreable":scoreable,
            "primary_exclusion_reason":primary,
            "secondary_exclusion_reasons":secondary,
            "exclusion_reasons":reasons,
            "maturity":{str(h):bool((ev.get("outcomes") or {}).get(str(h))) for h in HORIZONS},
            "scores":scores,
            "data_quality":hmeta,
            "source_provenance":prov,
            "point_in_time_status":pit,
            "market_timestamp_cutoff":"strictly_before_baseline_date",
        })
    scoreable_n=sum(1 for x in rows if x["scoreable"])
    if len(rows) != scoreable_n + sum(primary_counts.values()):
        raise AssertionError("EventScore conservation failed: total != scoreable + primary exclusions")
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "mode":"research_only_adapter",
        "counts":{
            "events":len(rows),
            "scoreable":scoreable_n,
            "primary_exclusion":dict(primary_counts),
            "conservation_ok":len(rows)==scoreable_n+sum(primary_counts.values()),
        },
        "events":rows,
        "guardrails":[
            "Legacy outcomes remain available; EventScore is an adapter, not an in-place rewrite.",
            "Unknown entry semantics never enter method performance.",
            "STOOQ archive is canonical; cache only fills gaps after overlap consistency checks.",
            "Every non-scoreable event has exactly one primary exclusion reason; the conservation equation is enforced.",
            "Price conflicts, cache-only histories, pre-ingest historical evidence and option structures stay unscored."
        ]
    }

def build_cache_coverage_audit(result,histories):
    rows=[]
    for ev in result.get("events") or []:
        if not ev.get("rule_id"):continue
        if (ev.get("data_quality") or {}).get("status")!="cache_only_unscored":continue
        sym=ev.get("symbol")
        meta=(histories.get(sym) or {}).get("meta") or {}
        rows.append({
            "event_id":ev.get("event_id"),
            "rule_id":ev.get("rule_id"),
            "symbol":sym,
            "author":ev.get("author"),
            "entry_type":ev.get("entry_type"),
            "local_stooq_archive_present":False,
            "cache_present":True,
            "classification":"local_archive_not_provisioned_or_mapping_unknown",
            "note":"This proves absence from the local STOOQ watchlist archive, not absence from the STOOQ service. Upstream STOOQ service coverage must be audited separately before any fallback policy is chosen.",
            "price_series_hash":meta.get("price_series_hash"),
        })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "events":rows,
        "counts":{
            "events":len(rows),
            "symbols":len({x["symbol"] for x in rows}),
        },
    }

def build_histories():
    stooq=read_archive();cache=read_cache()
    syms=set(stooq)|set(cache)
    out={}
    for s in syms:
        df,meta=reconcile_history(stooq.get(s),cache.get(s))
        out[s]={"df":df,"meta":meta}
    return out

def main():
    validation=load(VALIDATION,{})
    registry=load(REGISTRY,{})
    histories=build_histories()
    result=adapt(validation,registry,histories,load_spec(),load(SOURCE_STORE,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    comparison={
        "version":VERSION,
        "generated_at":result["generated_at"],
        "legacy_events":len(validation.get("events") or []),
        "eventscore_events":result["counts"]["events"],
        "eventscore_scoreable":result["counts"]["scoreable"],
        "primary_exclusion":result["counts"]["primary_exclusion"],
        "conservation_ok":result["counts"]["conservation_ok"],
        "note":"Old outcomes are retained; differences reflect stricter entry/data-quality/spec eligibility, not overwritten history."
    }
    COMPARE.parent.mkdir(parents=True,exist_ok=True)
    COMPARE.write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding="utf-8")
    audit=build_cache_coverage_audit(result,histories)
    CACHE_AUDIT.parent.mkdir(parents=True,exist_ok=True)
    CACHE_AUDIT.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"counts":result["counts"],"cache_audit":audit["counts"]},ensure_ascii=False))

if __name__=="__main__":main()
