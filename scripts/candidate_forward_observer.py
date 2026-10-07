#!/usr/bin/env python3
"""Candidate Forward Observer v1.0.

Append-only, point-in-time observation ledger for fully reproducible compiled
candidate rules. This is Research/Shadow evidence only.

Rules:
- only forward_observation_eligible + machine_ready_shadow candidates;
- only canonical local STOOQ history can create scoreable Forward observations;
- no historical backfill: only the latest completed bar can create a state-entry;
- candidate formation must predate the observed trading date;
- state-entry only, not repeated daily snapshots;
- next-session open is appended as the point-in-time evaluation baseline;\n- 5/20/60 outcomes append as separate immutable records;
- hash chain makes accidental rewriting detectable;
- no Promotion/Production mutation and no orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from candidate_rule_replay import condition_series, event_regime, qqq_return
    from local_history_agent import read_archive
except ModuleNotFoundError:
    from scripts.candidate_rule_replay import condition_series, event_regime, qqq_return
    from scripts.local_history_agent import read_archive

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"registry"/"candidate_rules.json"
LEDGER=ROOT/"research"/"history"/"candidate_forward_events.jsonl"
STATUS=ROOT/"docs"/"research"/"candidate_forward_status.json"
VERSION="1.1"
HORIZONS=(5,20,60)

def load_json(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def load_ledger(path=LEDGER):
    rows=[]
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():rows.append(json.loads(line))
    except Exception:pass
    return rows

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def record_hash(record):
    payload={k:v for k,v in record.items() if k!="record_hash"}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()

def verify_chain(rows):
    prev=None
    for row in rows:
        if row.get("prev_hash")!=prev:return False
        if row.get("record_hash")!=record_hash(row):return False
        prev=row.get("record_hash")
    return True

def append_record(rows,record):
    out=dict(record)
    out["prev_hash"]=rows[-1].get("record_hash") if rows else None
    out["record_hash"]=record_hash(out)
    rows.append(out)
    return out

def source_observation_map(registry):
    return {str(x.get("source_id")):x for x in registry.get("source_observations") or [] if x.get("source_id")}

def eligible_candidates(registry):
    return [
        c for c in registry.get("candidates") or []
        if c.get("forward_observation_eligible") is True
        and c.get("reproducibility_status")=="machine_ready_shadow"
        and not (c.get("unresolved_inputs") or [])
        and c.get("formation_mode")=="forward_initial"
    ]

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def active_series(candidate,df):
    needed=[]
    for cond in candidate.get("conditions") or []:
        if cond.get("semantic_role") in {"prior_observation","invalidation"}:
            # Temporal-transition candidates should already be ineligible until
            # their sequence/window is explicitly defined.
            return None
        s=condition_series(df,cond)
        if s is None:return None
        needed.append(s.fillna(False))
    if not needed:return None
    active=needed[0].copy()
    for s in needed[1:]:active=active & s
    return active

def event_id(candidate,symbol,event_date):
    raw=f"{candidate.get('candidate_id')}|{symbol}|{event_date}|state_entry"
    return "cfwd_"+hashlib.sha256(raw.encode()).hexdigest()[:24]

def existing_keys(rows):
    entries={x.get("event_id") for x in rows if x.get("record_type")=="state_entry"}
    baselines={x.get("event_id") for x in rows if x.get("record_type")=="baseline"}
    outcomes={(x.get("event_id"),int(x.get("horizon"))) for x in rows if x.get("record_type")=="outcome" and x.get("horizon") is not None}
    return entries,baselines,outcomes

def formation_date(candidate,obs_map):
    obs=obs_map.get(str(candidate.get("source_id"))) or {}
    raw=obs.get("first_candidate_compiler_seen_at")
    try:return pd.Timestamp(raw).date() if raw else None
    except Exception:return None

def maybe_state_entry(candidate,store,obs_map,rows,now):
    syms=list((candidate.get("scope") or {}).get("symbols") or [])
    if len(syms)!=1:return None,"single_symbol_scope_required"
    symbol=str(syms[0]).upper()
    df=store.get(symbol)
    if df is None or df.empty:return None,"canonical_stooq_history_missing"
    df=df.sort_index()
    df=df[~df.index.duplicated(keep="last")]
    if len(df)<51:return None,"history_too_short"
    active=active_series(candidate,df)
    if active is None:return None,"unsupported_or_temporal_condition"
    i=len(df)-1
    latest_date=df.index[i].date()
    formed=formation_date(candidate,obs_map)
    if formed is None:return None,"candidate_formation_time_missing"
    # Strict anti-backfill: formation must be before the observed trading date.
    if latest_date<=formed:return None,"awaiting_post_formation_completed_bar"
    current=bool(active.iloc[i])
    previous=bool(active.iloc[i-1]) if i>0 else False
    if not current or previous:return None,"no_new_state_entry"
    eid=event_id(candidate,symbol,latest_date.isoformat())
    entries,_,_=existing_keys(rows)
    if eid in entries:return None,"already_recorded"
    close=finite(df.iloc[i]["close"])
    if close is None:return None,"invalid_close"
    qqq=store.get("QQQ")
    rec={
        "ledger_version":VERSION,
        "record_type":"state_entry",
        "recorded_at":now,
        "event_id":eid,
        "candidate_id":candidate.get("candidate_id"),
        "family_signature":candidate.get("family_signature"),
        "source_id":candidate.get("source_id"),
        "proposition_id":candidate.get("proposition_id"),
        "symbol":symbol,
        "signal_date":latest_date.isoformat(),
        "signal_close":close,
        "expected_direction":"bearish" if candidate.get("state_role")=="invalidation_or_risk" else "bullish",
        "regime_at_signal":event_regime(qqq,latest_date.isoformat()),
        "data_source":"local_stooq_archive",
        "evidence_class":"genuine_forward_state_entry",
        "scoreable_for_forward":False,
        "scoreability_reason":"awaiting_next_session_open_baseline",
        "production_eligible":False,
    }
    return append_record(rows,rec),None

def maybe_baseline(entry,store,rows,now):
    symbol=str(entry.get("symbol") or "")
    df=store.get(symbol)
    if df is None or df.empty:return None,"canonical_stooq_history_missing"
    df=df.sort_index();df=df[~df.index.duplicated(keep="last")]
    signal_ts=pd.Timestamp(entry.get("signal_date"))
    if signal_ts not in df.index:return None,"signal_date_missing"
    pos=df.index.get_loc(signal_ts)
    if not isinstance(pos,int) or pos+1>=len(df):return None,"awaiting_next_session_open"
    baseline_pos=pos+1
    baseline_open=finite(df.iloc[baseline_pos]["open"])
    if baseline_open in (None,0):return None,"invalid_next_session_open"
    baseline_date=df.index[baseline_pos].date().isoformat()
    rec={
        "ledger_version":VERSION,
        "record_type":"baseline",
        "recorded_at":now,
        "event_id":entry.get("event_id"),
        "candidate_id":entry.get("candidate_id"),
        "family_signature":entry.get("family_signature"),
        "symbol":symbol,
        "signal_date":entry.get("signal_date"),
        "baseline_date":baseline_date,
        "baseline_open":baseline_open,
        "entry_semantics":"next_session_open_after_completed_daily_signal",
        "data_source":"local_stooq_archive",
        "evidence_class":"genuine_forward_evaluation_baseline",
        "scoreable_for_forward":True,
        "production_eligible":False,
    }
    return append_record(rows,rec),None

def qqq_open_to_close_return(qqq,baseline_date,h):
    if qqq is None or qqq.empty:return None
    qqq=qqq.sort_index();qqq=qqq[~qqq.index.duplicated(keep="last")]
    ts=pd.Timestamp(baseline_date)
    if ts not in qqq.index:return None
    pos=qqq.index.get_loc(ts)
    if not isinstance(pos,int) or pos+h>=len(qqq):return None
    a=finite(qqq.iloc[pos]["open"]);b=finite(qqq.iloc[pos+h]["close"])
    return None if a in (None,0) or b is None else b/a-1.0

def mature_outcome(baseline,h,store,now):
    symbol=str(baseline.get("symbol") or "")
    df=store.get(symbol)
    if df is None or df.empty:return None
    df=df.sort_index();df=df[~df.index.duplicated(keep="last")]
    ts=pd.Timestamp(baseline.get("baseline_date"))
    if ts not in df.index:return None
    pos=df.index.get_loc(ts)
    if not isinstance(pos,int) or pos+h>=len(df):return None
    entry=finite(baseline.get("baseline_open"))
    if entry in (None,0):return None
    end=finite(df.iloc[pos+h]["close"])
    if end is None:return None
    path=df.iloc[pos:pos+h+1]
    lows=[finite(x) for x in path["low"].tolist()]; lows=[x for x in lows if x is not None]
    highs=[finite(x) for x in path["high"].tolist()]; highs=[x for x in highs if x is not None]
    ret=end/entry-1.0
    qqq=store.get("QQQ")
    bench=qqq_open_to_close_return(qqq,baseline.get("baseline_date"),h)
    return {
        "ledger_version":VERSION,
        "record_type":"outcome",
        "recorded_at":now,
        "event_id":baseline.get("event_id"),
        "candidate_id":baseline.get("candidate_id"),
        "family_signature":baseline.get("family_signature"),
        "symbol":symbol,
        "baseline_date":baseline.get("baseline_date"),
        "horizon":h,
        "maturity_date":df.index[pos+h].date().isoformat(),
        "return":ret,
        "mae":min(lows)/entry-1.0 if lows else None,
        "mfe":max(highs)/entry-1.0 if highs else None,
        "benchmark_return":bench,
        "excess_vs_qqq":ret-bench if bench is not None else None,
        "evidence_class":"genuine_forward_outcome",
        "scoreable_for_forward":True,
        "production_eligible":False,
    }

def build(registry,store,prior_rows=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    rows=[dict(x) for x in (prior_rows or [])]
    if rows and not verify_chain(rows):
        return rows,{
            "version":VERSION,"generated_at":now,"status":"fail_closed_hash_chain_invalid",
            "counts":{"eligible_candidates":0,"state_entries":0,"evaluation_baselines":0,"outcomes_5":0,"outcomes_20":0,"outcomes_60":0},
            "production_effect":"none","promotion_effect":"none",
        }
    obs_map=source_observation_map(registry)
    elig=eligible_candidates(registry)
    diagnostics=[]
    for candidate in elig:
        _,reason=maybe_state_entry(candidate,store,obs_map,rows,now)
        diagnostics.append({"candidate_id":candidate.get("candidate_id"),"observation":reason or "state_entry_appended"})
    entries,baselines,outcomes=existing_keys(rows)
    for entry in [x for x in rows if x.get("record_type")=="state_entry"]:
        if entry.get("event_id") not in baselines:
            rec,_=maybe_baseline(entry,store,rows,now)
            if rec:baselines.add(entry.get("event_id"))
    baseline_by={x.get("event_id"):x for x in rows if x.get("record_type")=="baseline"}
    for baseline in baseline_by.values():
        for h in HORIZONS:
            if (baseline.get("event_id"),h) in outcomes:continue
            rec=mature_outcome(baseline,h,store,now)
            if rec:
                append_record(rows,rec)
                outcomes.add((baseline.get("event_id"),h))
    counts={
        "eligible_candidates":len(elig),
        "state_entries":sum(1 for x in rows if x.get("record_type")=="state_entry"),
        "evaluation_baselines":sum(1 for x in rows if x.get("record_type")=="baseline"),
        "outcomes_5":sum(1 for x in rows if x.get("record_type")=="outcome" and x.get("horizon")==5),
        "outcomes_20":sum(1 for x in rows if x.get("record_type")=="outcome" and x.get("horizon")==20),
        "outcomes_60":sum(1 for x in rows if x.get("record_type")=="outcome" and x.get("horizon")==60),
    }
    status={
        "version":VERSION,
        "generated_at":now,
        "status":"running",
        "ledger_mode":"append_only_hash_chained_state_entry_next_open_baseline",
        "counts":counts,
        "diagnostics":diagnostics[:40],
        "forward_evidence_mixed":False,
        "historical_backfill_allowed":False,
        "canonical_score_source":"local_stooq_archive",
        "promotion_bridge":"existing_spec_1_7_governance_only_after_mature_forward_outcomes",
        "production_effect":"none",
        "promotion_effect":"none",
        "guardrails":[
            "Only forward_initial, fully reproducible candidates may be observed.",
            "Only the latest completed canonical STOOQ bar may create a state-entry; historical state entries are never backfilled.",
            "Candidate formation must predate the observed trading date.",
            "A completed daily signal is evaluated from the next trading session open, never the same-day close.",
            "5/20/60 outcomes append from that next-open baseline and never rewrite earlier records.",
            "Hash-chain failure closes the ledger.",
            "This observer cannot alter Promotion Gate, protected rules, positions, sizing or orders.",
        ],
    }
    return rows,status

def write_ledger(rows,path=LEDGER):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text("".join(canonical(x)+"\n" for x in rows),encoding="utf-8")

def main():
    registry=load_json(REGISTRY,{"candidates":[]})
    prior=load_ledger()
    rows,status=build(registry,read_archive(),prior)
    if status.get("status")=="fail_closed_hash_chain_invalid":
        STATUS.parent.mkdir(parents=True,exist_ok=True)
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        raise SystemExit("candidate forward ledger hash chain invalid")
    write_ledger(rows)
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(status["counts"],ensure_ascii=False))

if __name__=="__main__":main()
