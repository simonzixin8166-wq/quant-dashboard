#!/usr/bin/env python3
"""V6.15.8a EventScore integrity adapter.

This module adapts existing Source Outcome events to one versioned score format.
It does not replace the legacy engines yet.
"""
from __future__ import annotations
import hashlib, json, math, sys
from collections import Counter
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
VALIDATION=ROOT/"docs"/"research"/"source_outcome_validation.json"
REGISTRY=ROOT/"research"/"registry"/"rules.json"
OUT=ROOT/"research"/"events"/"event_scores_v1.json"
COMPARE=ROOT/"research"/"audit"/"v615_eventscore_comparison.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"

sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import load_spec,direction_adjusted_return
from entry_semantics import classify_event
from local_history_agent import read_archive
from source_history_cache import read_cache

VERSION="6.15.8l"
SCORING_ENGINE_VERSION="event_score@6.15.8l"
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
    """STOOQ is canonical and scoreable histories never splice multiple sources."""
    if stooq is None or stooq.empty:
        if cache is None or cache.empty:
            return None,{"status":"missing","source":"none","price_source":"none","adjustment_basis":None,"price_series_hash":None}
        # Without canonical STOOQ this is context-only, never scoreable.
        c=cache.copy().sort_index()
        return c,{
            "status":"cache_only_unscored",
            "source":"yfinance_validation_cache",
            "price_source":"yfinance_validation_cache",
            "adjustment_basis":"yfinance_auto_adjust_false_native_ohlc",
            "same_source_only":True,
            "price_series_hash":frame_hash(c),
        }
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
    return base,{
        "status":status,
        "source":"stooq_archive",
        "price_source":"stooq_archive",
        "adjustment_basis":"stooq_archive_native_series",
        "same_source_only":True,
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
    return classify_event(event).get("entry_type") or "unknown"

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

def family_direction_map(families,spec):
    out={}
    current_hash=((spec.get("definitions") or {}).get("rule_family_definition_hash"))
    for a in families.get("assignments") or []:
        if not a.get("active"):continue
        if current_hash and a.get("definition_hash")!=current_hash:continue
        rid=a.get("rule_id")
        if rid is None:continue
        out[str(rid)]=((a.get("family_key") or {}).get("direction"))
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
            "first_fetched_at_origin":row.get("first_fetched_at_origin"),
            "admission_class":row.get("admission_class"),
            "admission_origin":row.get("admission_origin"),
            "identity_parent_source_key":row.get("identity_parent_source_key"),
            "published_at_semantics":row.get("published_at_semantics"),
            "timestamp_confidence":row.get("timestamp_confidence"),
            "snapshot_hash":row.get("snapshot_hash"),
        }
    return out

def baseline_timestamp_utc(baseline_date,spec=None):
    """Conservative tradable baseline instant for daily US equity OHLC.

    A daily bar's baseline date is anchored to the US regular-session open.
    This prevents a source first seen during that session from consuming any
    part of the same daily bar as point-in-time evidence.
    """
    if not baseline_date:return None
    cfg=((spec or {}).get("definitions") or {}).get("point_in_time_eligibility") or {}
    try:
        day=pd.Timestamp(str(baseline_date)[:10]).date()
        eastern=ZoneInfo("America/New_York")
        local=datetime.combine(day,time(9,30),tzinfo=eastern)
        return local.astimezone(timezone.utc)
    except Exception:
        return None

def point_in_time_status(prov,baseline_date,spec=None):
    first=(prov or {}).get("first_fetched_at")
    cfg=((spec or {}).get("definitions") or {}).get("point_in_time_eligibility") or {}
    admission_cfg=cfg.get("source_admission") or {}
    if admission_cfg:
        required_class=admission_cfg.get("genuine_forward_required_class","genuine_forward")
        if (prov or {}).get("admission_class")!=required_class:
            return "source_not_genuine_forward"
        if (prov or {}).get("first_fetched_at_origin")!="source_store_first_observation":
            return "source_not_genuine_forward"
    if not first or not baseline_date:
        return "unknown"
    try:
        first_ts=pd.Timestamp(first)
        if first_ts.tzinfo is None:
            return "unknown"
        first_utc=first_ts.tz_convert("UTC")
        if admission_cfg:
            foundation=pd.Timestamp(cfg.get("evidence_foundation_start_utc"))
            if foundation.tzinfo is None:
                return "unknown"
            if first_utc<foundation.tz_convert("UTC"):
                return "source_not_genuine_forward"
        baseline_utc=baseline_timestamp_utc(baseline_date,spec)
        if baseline_utc is None:
            return "unknown"
        return "eligible" if baseline_utc>first_utc.to_pydatetime() else "historical_pre_ingest"
    except Exception:
        return "unknown"

def resolve_price_provenance(event,hmeta):
    """Resolve event-level price provenance without depending on writer ordering.

    New Source Outcome artifacts may carry explicit provenance. Older/stale
    artifacts are deterministically upgraded from the same whole-symbol history
    metadata used by EventScore. No performance information is consulted.
    """
    explicit=dict((event or {}).get("price_provenance") or {})
    source=hmeta.get("price_source") or hmeta.get("source")
    adjustment=hmeta.get("adjustment_basis")
    if explicit:
        explicit.setdefault("provenance_origin","source_outcome_artifact")
        return explicit
    if source and source!="none" and adjustment:
        return {
            "price_source":source,
            "adjustment_basis":adjustment,
            "baseline_source":source,
            "horizon_source":source,
            "same_source":bool(hmeta.get("same_source_only",True)),
            "provenance_origin":"eventscore_deterministic_history_policy",
        }
    return {}

def exclusion_reasons(rid,triggered,direction,entry_type,data_status,point_status,structural_direction=None,price_provenance=None):
    price_provenance=price_provenance or {}
    reasons=[]
    if not rid:reasons.append("missing_rule_id")
    if not triggered:reasons.append("not_triggered")
    if direction=="option_structure":reasons.append("missing_real_option_pnl")
    elif direction not in {"bullish","bearish"}:reasons.append("unsupported_direction")
    if structural_direction in {"mixed_direction","unknown"} and "unsupported_direction" not in reasons:
        reasons.append("unsupported_direction")
    if entry_type=="unknown":reasons.append("unknown_entry_semantics")
    px_source=price_provenance.get("price_source")
    adjustment=price_provenance.get("adjustment_basis")
    baseline_source=price_provenance.get("baseline_source")
    horizon_source=price_provenance.get("horizon_source")
    same_source=price_provenance.get("same_source")
    if not px_source or not adjustment or not baseline_source or not horizon_source or same_source is not True or baseline_source!=horizon_source:
        reasons.append("price_provenance_incomplete")
    if data_status=="conflict":reasons.append("price_source_conflict")
    elif data_status=="cache_only_unscored":reasons.append("cache_only_unscored")
    elif data_status!="ok":reasons.append("missing_price_data")
    if point_status in {"historical_pre_ingest","source_not_genuine_forward"}:reasons.append("non_point_in_time_source")
    elif point_status=="unknown":reasons.append("timestamp_provenance_unknown")
    return reasons

DEFAULT_PRIMARY_PRECEDENCE=(
    "non_point_in_time_source",
    "timestamp_provenance_unknown",
    "missing_rule_id",
    "missing_real_option_pnl",
    "unsupported_direction",
    "unknown_entry_semantics",
    "not_triggered",
    "price_provenance_incomplete",
    "price_source_conflict",
    "cache_only_unscored",
    "missing_price_data",
)

def choose_primary(reasons,spec=None):
    precedence=((spec or {}).get("definitions") or {}).get("primary_exclusion_precedence") or DEFAULT_PRIMARY_PRECEDENCE
    for key in precedence:
        if key in reasons:return key
    return None

def adapt(validation,registry,histories=None,spec=None,source_store=None,families=None):
    spec=spec or load_spec()
    mapping=registry_map(registry)
    histories=histories or {}
    provenance=source_provenance_map(source_store or {})
    structural_directions=family_direction_map(families or {},spec)
    rows=[]
    primary_counts=Counter()
    for ev in validation.get("events") or []:
        sid,op_idx,symbol,_=parse_event_identity(ev)
        rid=mapping.get((str(sid),op_idx))
        entry_meta=classify_event(ev)
        et=entry_meta.get("entry_type") or "unknown"
        direction=direction_from_event(ev)
        structural_direction=structural_directions.get(str(rid)) if rid is not None else None
        hmeta=histories.get(symbol,{}).get("meta") or {}
        prov=provenance.get(str(sid)) or {}
        baseline_ts=baseline_timestamp_utc(ev.get("baseline_date"),spec)
        pit=point_in_time_status(prov,ev.get("baseline_date"),spec)
        price_provenance=resolve_price_provenance(ev,hmeta)
        reasons=exclusion_reasons(rid,bool(ev.get("triggered")),direction,et,hmeta.get("status"),pit,structural_direction,price_provenance)
        primary=choose_primary(reasons,spec)
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
                "horizon_end_date":old.get("date"),
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
            "scoring_engine_version":SCORING_ENGINE_VERSION,
            "author":ev.get("author"),
            "symbol":symbol,
            "published_at":ev.get("published_at"),
            "baseline_date":ev.get("baseline_date"),
            "baseline_timestamp_utc":baseline_ts.isoformat() if baseline_ts is not None else None,
            "entry_type":et,
            "fill_status":entry_meta.get("fill_status"),
            "fill_confidence":entry_meta.get("fill_confidence"),
            "fill_model":entry_meta.get("fill_model"),
            "entry_inference_source":entry_meta.get("inference_source"),
            "entry_registry_version":entry_meta.get("registry_version"),
            "direction":direction,
            "rule_structural_direction":structural_direction,
            "triggered":bool(ev.get("triggered")),
            "scoreable":scoreable,
            "primary_exclusion_reason":primary,
            "secondary_exclusion_reasons":secondary,
            "exclusion_reasons":reasons,
            "maturity":{str(h):bool((ev.get("outcomes") or {}).get(str(h))) for h in HORIZONS},
            "scores":scores,
            "data_quality":hmeta,
            "price_provenance":price_provenance,
            "source_provenance":prov,
            "point_in_time_status":pit,
            "market_timestamp_cutoff":"strictly_before_baseline_timestamp_utc",
        })
    scoreable_n=sum(1 for x in rows if x["scoreable"])
    if len(rows) != scoreable_n + sum(primary_counts.values()):
        raise AssertionError("EventScore conservation failed: total != scoreable + primary exclusions")
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "scoring_engine_version":SCORING_ENGINE_VERSION,
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
            "Mixed/unknown Rule Family structural direction always fails closed even if a legacy outcome labels the event bullish or bearish.",
            "STOOQ archive is canonical; scoreable histories never splice STOOQ and cache rows inside one event.",
            "Baseline and horizon price provenance plus adjustment basis must be explicit or deterministically resolved from the same whole-symbol history policy; otherwise the event fails closed.",
            "EventScore provenance resolution is result-blind and protects against Source Outcome / Research Evidence workflow ordering lag.",
            "Every mature horizon carries the exact realized horizon_end_date from the source outcome record for dependence clustering.",
            "Every non-scoreable event has exactly one primary exclusion reason; the conservation equation is enforced.",
            "Price conflicts, cache-only histories, pre-ingest historical evidence and option structures stay unscored."
        ]
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
    result=adapt(validation,registry,histories,load_spec(),load(SOURCE_STORE,{}),load(FAMILIES,{}))
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
    print(json.dumps(result["counts"],ensure_ascii=False))

if __name__=="__main__":main()
