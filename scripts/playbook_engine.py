#!/usr/bin/env python3
"""V6.10a Opportunity Playbook state engine + silent Forward Ledger bridge.

This engine does not trade, size positions, or read private brokerage data.
It standardizes the three existing public market Playbooks, applies a minimum
quality gate, emits a public sanitized status snapshot, and (when explicitly
configured) appends state transitions to a separate private GitHub ledger.
"""
from __future__ import annotations

import hashlib, json, os, subprocess
from datetime import datetime, timezone, date
from pathlib import Path

from playbook_config import PLAYBOOKS, rule_hash
from private_ledger import PrivateGitHubLedger, aggregate_anchor
from trading_calendar import expected_latest_completed_session, sessions_between

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs"/"data.json"
HISTORY=ROOT/"docs"/"research"/"historical_journal.json"
STATUS_OUT=ROOT/"docs"/"research"/"playbook_status.json"
ANCHOR_OUT=ROOT/"docs"/"research"/"ledger_anchor.json"

ENGINE_VERSION="6.10a.0"
SCHEMA_VERSION="1.0"

def load(path,default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def git_sha():
    env=os.getenv("GITHUB_SHA","").strip()
    if env:return env
    try:return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:return "unknown"

def truthy_env(name,default=True):
    raw=os.getenv(name)
    if raw is None:return default
    return str(raw).strip().lower() not in {"0","false","no","off",""}

def record_id(*parts):
    raw="|".join("" if x is None else str(x) for x in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]

def now_iso(now):
    return now.astimezone(timezone.utc).isoformat()

def parse_date(value):
    try:return date.fromisoformat(str(value)[:10])
    except Exception:return None

def _asset_row(data,symbol):
    if symbol in (data.get("core") or {}):return (data.get("core") or {}).get(symbol) or {}
    if symbol in (data.get("index") or {}):return (data.get("index") or {}).get(symbol) or {}
    if symbol in (data.get("stocks") or {}):return (data.get("stocks") or {}).get(symbol) or {}
    return {}

def _quarantine_map(history):
    out={}
    for row in ((history.get("update") or {}).get("quarantined") or []):
        sym=str(row.get("symbol") or "").upper()
        if sym:out.setdefault(sym,[]).append(row)
    return out

def quality_gate(data,history,now=None):
    now=now or datetime.now(timezone.utc)
    market_date=str(data.get("spy_date") or data.get("updated") or "")[:10]
    observed=parse_date(market_date)
    expected=expected_latest_completed_session(now)
    missing=sessions_between(observed,expected) if observed and observed<expected else []
    global_reasons=[]
    if not observed:global_reasons.append("missing_market_date")
    elif observed!=expected:
        global_reasons.append("market_date_not_latest_completed_session")
    quarantine=_quarantine_map(history)
    return {
        "market_date":market_date or None,
        "expected_market_date":expected.isoformat(),
        "fresh":not global_reasons,
        "global_reasons":global_reasons,
        "missing_sessions":[d.isoformat() for d in missing],
        "quarantine":quarantine,
        "checked_at":now_iso(now),
    }

def _split_ratio_candidate(close,prev):
    """Conservative corporate-action gate for common split/reverse-split ratios.

    A candidate is quarantined for review rather than treated as a market signal.
    This intentionally favors false-positive quarantine over contaminating an
    append-only Forward ledger with an unadjusted price discontinuity.
    """
    try:
        close=float(close);prev=float(prev)
        if close<=0 or prev<=0:return False
        ratio=close/prev
    except Exception:
        return False
    common=(0.5,1/3,0.25,0.2,2.0,3.0,4.0,5.0,10.0)
    if any(abs(ratio-target)/target<=0.08 for target in common):
        return True
    return abs(ratio-1.0)>0.60

def symbol_quality(symbol,data,history,gate,require_ath=False):
    row=_asset_row(data,symbol)
    reasons=[]
    market_date=gate.get("market_date")
    if gate.get("global_reasons"):reasons.extend(gate["global_reasons"])
    if not row:reasons.append("missing_asset_row")
    elif str(row.get("date") or "")[:10]!=market_date:reasons.append("asset_date_mismatch")
    close=row.get("close");prev=row.get("prev_close")
    try:
        if float(close)<=0:reasons.append("invalid_close")
        if prev is not None and float(prev)>0 and _split_ratio_candidate(close,prev):
            reasons.append("split_or_adjustment_candidate")
    except Exception:
        reasons.append("invalid_price")
    if require_ath and row.get("ath_validation")!="PASS":
        reasons.append("adjusted_ath_not_verified")
    if str(symbol).upper() in gate.get("quarantine",{}):
        reasons.append("history_quarantined")
    return {
        "eligible":not reasons,
        "reasons":sorted(set(reasons)),
        "date":str(row.get("date") or "")[:10] or None,
        "source":"docs/data.json",
        "as_of":str(row.get("date") or "")[:10] or None,
        "freshness":"fresh" if not reasons else "failed",
        "split_adjustment_check":"pass" if not any(x in reasons for x in ("split_or_adjustment_candidate","adjusted_ath_not_verified","history_quarantined")) else "fail",
    }

def _state_row(playbook_id,symbol,state,detail,market_date,quality,metrics=None,baseline_close=None,benchmark="QQQ"):
    rh=rule_hash(playbook_id)
    return {
        "entity_key":f"{playbook_id}:{symbol}",
        "playbook_id":playbook_id,
        "symbol":symbol,
        "state":state,
        "detail":detail,
        "state_key":f"{state}:{detail}",
        "market_date":market_date,
        "rule_version":PLAYBOOKS[playbook_id].get("rule_version"),
        "rule_hash":rh,
        "quality":quality,
        "baseline_close":baseline_close,
        "benchmark":benchmark,
        "metrics":metrics or {},
    }

def evaluate_cp01(data,history,gate):
    pb=PLAYBOOKS["CP-01"];rows=[]
    for symbol in pb["assets"]:
        q=symbol_quality(symbol,data,history,gate,require_ath=True)
        asset=_asset_row(data,symbol)
        if not q["eligible"]:
            rows.append(_state_row("CP-01",symbol,"UNDETERMINED","|".join(q["reasons"]) or "quality_failed",gate["market_date"],q))
            continue
        level=int(asset.get("level") or 0)
        state="TRIGGERED" if level>=1 else "IDLE"
        detail=f"tier{level}" if level>=1 else "normal"
        rows.append(_state_row("CP-01",symbol,state,detail,gate["market_date"],q,
            metrics={"level":level,"drawdown":asset.get("strategy_drawdown")},
            baseline_close=asset.get("close")))
    return rows

def evaluate_cp02(data,history,gate):
    q=symbol_quality("QQQ",data,history,gate,require_ath=False)
    x=data.get("tqqq_x2") or {}
    reasons=list(q["reasons"])
    if not x.get("available"):reasons.append("tqqq_strategy_unavailable")
    if str(x.get("date") or "")[:10]!=gate.get("market_date"):reasons.append("tqqq_strategy_date_mismatch")
    snap=x.get("snapshot") or {}
    if str(snap.get("date") or "")[:10]!=gate.get("market_date"):reasons.append("tqqq_snapshot_date_mismatch")
    q=dict(q);q["reasons"]=sorted(set(reasons));q["eligible"]=not q["reasons"];q["freshness"]="fresh" if q["eligible"] else "failed"
    if not q["eligible"]:
        return [_state_row("CP-02","TQQQ","UNDETERMINED","|".join(q["reasons"]) or "quality_failed",gate["market_date"],q)]
    rule=str(x.get("rule") or "hold")
    actions=set((PLAYBOOKS["CP-02"].get("trigger") or {}).get("action_rules") or [])
    state="TRIGGERED" if rule in actions else "IDLE"
    baseline=(data.get("index") or {}).get("QQQ",{}).get("close") or snap.get("qqq")
    return [_state_row("CP-02","TQQQ",state,rule,gate["market_date"],q,
        metrics={"target_position":x.get("target_position"),"target_daily_exposure":x.get("target_daily_exposure"),"vix":snap.get("vix")},
        baseline_close=baseline)]

def evaluate_cp03(data,history,gate):
    pb=PLAYBOOKS["CP-03"]
    source={str(x.get("symbol")):x for x in ((data.get("leaps_radar") or {}).get("assets") or [])}
    rows=[]
    for symbol in pb["assets"]:
        q=symbol_quality(symbol,data,history,gate,require_ath=False)
        item=source.get(symbol) or {}
        reasons=list(q["reasons"])
        if not item.get("available"):reasons.append("leaps_signal_unavailable")
        if str(item.get("date") or "")[:10]!=gate.get("market_date"):reasons.append("leaps_signal_date_mismatch")
        q=dict(q);q["reasons"]=sorted(set(reasons));q["eligible"]=not q["reasons"];q["freshness"]="fresh" if q["eligible"] else "failed"
        if not q["eligible"]:
            rows.append(_state_row("CP-03",symbol,"UNDETERMINED","|".join(q["reasons"]) or "quality_failed",gate["market_date"],q))
            continue
        status=str(item.get("status") or "normal")
        state={"normal":"IDLE","watch":"NEAR_TRIGGER","candidate":"TRIGGERED","strong":"TRIGGERED"}.get(status,"UNDETERMINED")
        detail=status
        rows.append(_state_row("CP-03",symbol,state,detail,gate["market_date"],q,
            metrics={"drawdown63":item.get("drawdown63"),"rsi14":item.get("rsi14"),"trend_risk":item.get("trend_risk"),"vix_risk":item.get("vix_risk")},
            baseline_close=item.get("close")))
    return rows

def evaluate(data,history,now=None):
    gate=quality_gate(data,history,now)
    rows=[]
    if PLAYBOOKS["CP-01"].get("enabled"):rows+=evaluate_cp01(data,history,gate)
    if PLAYBOOKS["CP-02"].get("enabled"):rows+=evaluate_cp02(data,history,gate)
    if PLAYBOOKS["CP-03"].get("enabled"):rows+=evaluate_cp03(data,history,gate)
    return gate,rows

def _event(row,previous_key,now,commit_sha,record_type):
    pb=PLAYBOOKS[row["playbook_id"]]
    market_date=row["market_date"]
    rid=record_id(row["entity_key"],market_date,row["state_key"],row["rule_hash"],record_type)
    return {
        "schema_version":SCHEMA_VERSION,
        "record_type":record_type,
        "record_id":rid,
        "recorded_at":now_iso(now),
        "playbook_id":row["playbook_id"],
        "rule_version":row["rule_version"],
        "rule_hash":row["rule_hash"],
        "commit_sha":commit_sha,
        "entity_key":row["entity_key"],
        "symbol":row["symbol"],
        "market_date":market_date,
        "event_date":market_date,
        "state":row["state"],
        "state_detail":row["detail"],
        "previous_state_key":previous_key,
        "baseline_close":row.get("baseline_close"),
        "benchmark":row.get("benchmark"),
        "risk_band":pb.get("risk_band_per_event"),
        "data_lineage":[{
            "source":row["quality"].get("source"),
            "as_of":row["quality"].get("as_of"),
            "freshness":row["quality"].get("freshness"),
            "used_in_decision":True,
            "split_adjustment_check":row["quality"].get("split_adjustment_check"),
        }],
        "detected_at":now_iso(now),
        "detection_delay_sessions":0,
        "late_detected":False,
        "scoreable":row["state"]=="TRIGGERED",
        "evidence_provenance":"forward_out_of_sample",
    }

def _audit_event(kind,message,market_date,now,commit_sha,extra=None):
    payload={
        "schema_version":SCHEMA_VERSION,"record_type":"audit_event",
        "record_id":record_id("audit",kind,market_date,message),
        "recorded_at":now_iso(now),"playbook_id":"SYSTEM","rule_version":ENGINE_VERSION,
        "rule_hash":hashlib.sha256(ENGINE_VERSION.encode()).hexdigest(),
        "commit_sha":commit_sha,"market_date":market_date,"kind":kind,"message":message,
    }
    if extra:payload.update(extra)
    return payload

def build(now=None,writer=None):
    now=now or datetime.now(timezone.utc)
    data=load(DATA);history=load(HISTORY);previous=load(STATUS_OUT,{})
    gate,rows=evaluate(data,history,now)
    prev_rows={x.get("entity_key"):x for x in previous.get("playbooks") or []}
    global_enabled=truthy_env("MYALPHA_PLAYBOOK_ENABLED",True)
    global_ledger=truthy_env("MYALPHA_PLAYBOOK_LEDGER_ENABLED",True)
    alerts_enabled=truthy_env("MYALPHA_PLAYBOOK_ALERTS_ENABLED",False)
    writer=writer if writer is not None else PrivateGitHubLedger.from_env()
    storage_configured=bool(writer)
    forward_active=bool(storage_configured and global_enabled and global_ledger)
    previous_forward=bool((previous.get("storage") or {}).get("forward_clock_active"))
    starting_forward=forward_active and not previous_forward
    commit_sha=git_sha()

    trigger_events=[];audit_events=[];discipline_events=[]
    pending_by_entity={}

    if not gate["fresh"]:
        audit_events.append(_audit_event("heartbeat_or_freshness_failed",";".join(gate["global_reasons"]),gate["market_date"],now,commit_sha,{"expected_market_date":gate["expected_market_date"]}))
    if starting_forward:
        audit_events.append(_audit_event("forward_clock_started","Forward clock baseline established; current states are not backfilled as triggers.",gate["market_date"],now,commit_sha))

    for row in rows:
        old=prev_rows.get(row["entity_key"]) or {}
        old_key=old.get("committed_state_key") or old.get("state_key")
        same_rule=old.get("rule_hash")==row["rule_hash"] if old else False
        baseline_only=(not old) or (not same_rule) or starting_forward
        row["previous_state_key"]=old_key
        row["transition_detected"]=False
        row["bootstrap"]=baseline_only
        if baseline_only:
            if forward_active:
                audit_events.append(_audit_event("state_baseline",f'{row["entity_key"]} baseline {row["state_key"]}',gate["market_date"],now,commit_sha,{"entity_key":row["entity_key"],"rule_hash":row["rule_hash"]}))
            continue
        if row["state_key"]==old_key:
            continue
        row["transition_detected"]=True
        if not forward_active:
            continue
        if row["state"]=="UNDETERMINED":
            ev=_audit_event("undetermined",f'{row["entity_key"]}: {row["detail"]}',gate["market_date"],now,commit_sha,{"entity_key":row["entity_key"],"rule_hash":row["rule_hash"]})
            audit_events.append(ev);pending_by_entity[row["entity_key"]]=ev["record_id"]
        elif row["state"]=="NO_CHASE":
            ev=_event(row,old_key,now,commit_sha,"discipline_event")
            discipline_events.append(ev);pending_by_entity[row["entity_key"]]=ev["record_id"]
        else:
            ev=_event(row,old_key,now,commit_sha,"trigger_state_event")
            trigger_events.append(ev);pending_by_entity[row["entity_key"]]=ev["record_id"]

    ledger_health="not_configured" if not storage_configured else ("disabled" if not forward_active else "ok")
    anchor={
        "version":ENGINE_VERSION,"generated_at":now_iso(now),"market_date":gate["market_date"],
        "configured":storage_configured,"forward_clock_active":forward_active,
        "status":ledger_health,"root_hash":None,"streams":{}
    }
    write_ok=not forward_active
    results=[]
    if forward_active:
        try:
            for stream,events in (("trigger",trigger_events),("audit",audit_events),("discipline",discipline_events),("correction",[])):
                results.append(writer.append_many(stream,events,gate["market_date"] or now.date().isoformat()))
            a=aggregate_anchor(results)
            anchor.update(a);anchor["status"]="ok";write_ok=True
        except Exception as exc:
            ledger_health="write_failed";anchor["status"]="write_failed";anchor["error"]=str(exc)[:500]
            write_ok=False

    for row in rows:
        old=prev_rows.get(row["entity_key"]) or {}
        pending=pending_by_entity.get(row["entity_key"])
        if forward_active and pending and not write_ok:
            row["committed_state_key"]=old.get("committed_state_key") or old.get("state_key")
            row["pending_transition"]=True
        else:
            row["committed_state_key"]=row["state_key"]
            row["pending_transition"]=False

    status={
        "version":ENGINE_VERSION,"schema_version":SCHEMA_VERSION,"generated_at":now_iso(now),
        "market_date":gate["market_date"],"expected_market_date":gate["expected_market_date"],
        "mode":"silent_forward" if forward_active else "observe_only",
        "heartbeat":{
            "status":"pass" if gate["fresh"] else "fail",
            "scan_completed":True,
            "scan_completed_at":now_iso(now),
            "observed_market_date":gate["market_date"],
            "expected_market_date":gate["expected_market_date"],
            "missing_sessions":gate["missing_sessions"],
        },
        "data_quality":{
            "status":"pass" if gate["fresh"] and all(x["quality"]["eligible"] for x in rows) else "attention",
            "global_reasons":gate["global_reasons"],
            "undetermined_count":sum(1 for x in rows if x["state"]=="UNDETERMINED"),
            "split_adjustment_gate":True,
            "missing_session_gate":True,
            "freshness_gate":True,
        },
        "kill_switch":{
            "global_enabled":global_enabled,
            "ledger_enabled":global_ledger,
            "alerts_enabled":alerts_enabled,
        },
        "storage":{
            "configured":storage_configured,
            "forward_clock_active":forward_active,
            "health":anchor["status"],
            "raw_private":True,
            "public_output":"sanitized status + anchor only",
        },
        "counts":{
            "entities":len(rows),
            "triggered":sum(1 for x in rows if x["state"]=="TRIGGERED"),
            "near_trigger":sum(1 for x in rows if x["state"]=="NEAR_TRIGGER"),
            "undetermined":sum(1 for x in rows if x["state"]=="UNDETERMINED"),
            "transitions":sum(1 for x in rows if x["transition_detected"]),
            "private_trigger_events_pending":len(trigger_events),
        },
        "playbooks":rows,
        "private_playbooks":[{"playbook_id":"PP-01","class":"private","cloud_evaluated":False,"ledger":"private_decision_journal_only"}],
        "guardrails":[
            "No orders or position sizing.",
            "Private brokerage positions are not read by this engine.",
            "UNDETERMINED never enters scoreable Opportunity samples.",
            "Current baseline states are not backfilled as Forward triggers."
        ],
    }
    atomic_json(STATUS_OUT,status)
    atomic_json(ANCHOR_OUT,anchor)
    return status,anchor

def main():
    status,anchor=build()
    print(json.dumps({
        "version":status["version"],"mode":status["mode"],"market_date":status["market_date"],
        "heartbeat":status["heartbeat"]["status"],"storage":anchor["status"],"counts":status["counts"]
    },ensure_ascii=False))

if __name__=="__main__":
    main()
