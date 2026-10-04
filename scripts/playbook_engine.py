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
LEGACY_CP01_HASH="ad5eab7a409996693a01eea24dfeb9a2f070a27f535092a7cd079acee14972b9"
FORWARD_BASELINE_DATE="2026-10-02"
STABILIZATION_SESSIONS=10

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

def _pb_env(playbook_id, suffix):
    token=str(playbook_id).replace("-","_")
    return f"MYALPHA_{token}_{suffix}"

def runtime_switches():
    out={}
    for pid,pb in PLAYBOOKS.items():
        if pb.get("class")!="cloud":continue
        out[pid]={
            "enabled":truthy_env(_pb_env(pid,"ENABLED"),bool(pb.get("enabled",True))),
            "ledger_enabled":truthy_env(_pb_env(pid,"LEDGER_ENABLED"),bool(pb.get("ledger_enabled",True))),
            "notifications_enabled":truthy_env(_pb_env(pid,"NOTIFICATIONS_ENABLED"),bool(pb.get("notifications_enabled",False))),
            "source":"repository_variable_or_registry_default",
        }
    return out

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
        "lifecycle":PLAYBOOKS[playbook_id].get("lifecycle","active"),
        "evidence":PLAYBOOKS[playbook_id].get("evidence","unverified"),
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

def _continuity_meta(old,row):
    current_date=parse_date(row.get("market_date"))
    last_valid_date=parse_date(old.get("last_valid_market_date"))
    if old and old.get("state")!="UNDETERMINED" and not last_valid_date:
        last_valid_date=parse_date(old.get("market_date"))
    prior_valid_key=old.get("last_valid_state_key")
    if old and old.get("state")!="UNDETERMINED" and not prior_valid_key:
        prior_valid_key=old.get("committed_state_key") or old.get("state_key")

    if row.get("state")=="UNDETERMINED":
        return {
            "last_valid_state_key":prior_valid_key,
            "last_valid_market_date":last_valid_date.isoformat() if last_valid_date else None,
            "unknown_since_market_date":old.get("unknown_since_market_date") or row.get("market_date"),
            "detection_delay_sessions":0,
            "late_detected":False,
            "timing_uncertain":False,
            "detection_window_start":None,
            "detection_window_end":None,
        }

    unknown_since=old.get("unknown_since_market_date")
    gap_sessions=0
    late=False
    timing_uncertain=False
    window_start=None
    if old.get("state")=="UNDETERMINED" and last_valid_date and current_date:
        observed_gap=sessions_between(last_valid_date,current_date)
        # Current session is the actual detection session. Any earlier session
        # in this gap was unobserved/invalid and therefore contributes to delay.
        gap_sessions=max(0,len(observed_gap)-1)
        late=gap_sessions>0
        timing_uncertain=late
        if observed_gap:
            window_start=observed_gap[0].isoformat()
    return {
        "last_valid_state_key":row.get("state_key"),
        "last_valid_market_date":row.get("market_date"),
        "unknown_since_market_date":None,
        "detection_delay_sessions":gap_sessions,
        "late_detected":late,
        "timing_uncertain":timing_uncertain,
        "detection_window_start":window_start,
        "detection_window_end":row.get("market_date") if late else None,
        "previous_valid_state_key":prior_valid_key,
        "previous_valid_market_date":last_valid_date.isoformat() if last_valid_date else None,
        "prior_unknown_since_market_date":unknown_since,
    }

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
        "detection_delay_sessions":int((row.get("continuity") or {}).get("detection_delay_sessions") or 0),
        "late_detected":bool((row.get("continuity") or {}).get("late_detected")),
        "timing_uncertain":bool((row.get("continuity") or {}).get("timing_uncertain")),
        "detection_window_start":(row.get("continuity") or {}).get("detection_window_start"),
        "detection_window_end":(row.get("continuity") or {}).get("detection_window_end"),
        "previous_valid_state_key":(row.get("continuity") or {}).get("previous_valid_state_key"),
        "previous_valid_market_date":(row.get("continuity") or {}).get("previous_valid_market_date"),
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
    per_playbook=runtime_switches()
    previous_switches=((previous.get("kill_switch") or {}).get("per_playbook") or {})
    writer=writer if writer is not None else PrivateGitHubLedger.from_env()
    storage_configured=bool(writer)
    configured_repo=os.getenv("MYALPHA_LEDGER_REPO","").strip() or None
    token_present=bool(os.getenv("MYALPHA_LEDGER_TOKEN","").strip())
    if storage_configured:
        storage_reason="ready"
    elif configured_repo and not token_present:
        storage_reason="missing_token"
    elif token_present and not configured_repo:
        storage_reason="missing_repo"
    else:
        storage_reason="not_configured"
    forward_active=bool(storage_configured and global_enabled and global_ledger)
    previous_forward=bool((previous.get("storage") or {}).get("forward_clock_active"))
    starting_forward=forward_active and not previous_forward
    commit_sha=git_sha()

    trigger_events=[];audit_events=[];discipline_events=[];correction_events=[]
    pending_by_entity={}

    if not gate["fresh"]:
        audit_events.append(_audit_event("heartbeat_or_freshness_failed",";".join(gate["global_reasons"]),gate["market_date"],now,commit_sha,{"expected_market_date":gate["expected_market_date"]}))
    if starting_forward:
        audit_events.append(_audit_event("forward_clock_started","Forward clock baseline established; current states are not backfilled as triggers.",gate["market_date"],now,commit_sha))
    for pid,current in per_playbook.items():
        prior=previous_switches.get(pid) or {}
        current_view={k:current[k] for k in ("enabled","ledger_enabled","notifications_enabled")}
        prior_view={k:prior.get(k) for k in ("enabled","ledger_enabled","notifications_enabled")}
        if prior and current_view!=prior_view:
            audit_events.append(_audit_event(
                "playbook_kill_switch_changed",
                f"{pid} runtime switch changed by operator/repository variable.",
                gate["market_date"],now,commit_sha,
                {"playbook_id":pid,"previous":prior_view,"current":current_view,"human_controlled":True}
            ))

    legacy_cp01=any(
        x.get("playbook_id")=="CP-01" and x.get("rule_hash")==LEGACY_CP01_HASH
        for x in (previous.get("playbooks") or [])
    )
    if legacy_cp01 and any(x.get("playbook_id")=="CP-01" and x.get("rule_hash")!=LEGACY_CP01_HASH for x in rows):
        corr=_audit_event(
            "rule_hash_canonicalization_correction",
            "CP-01 rule_hash now includes its existing core_tiers dependencies; trading thresholds and semantics are unchanged.",
            gate["market_date"],now,commit_sha,
            {"playbook_id":"CP-01","old_rule_hash":LEGACY_CP01_HASH,"new_rule_hash":rule_hash("CP-01"),"semantic_change":False}
        )
        corr["record_type"]="correction_event"
        correction_events.append(corr)

    for row in rows:
        old=prev_rows.get(row["entity_key"]) or {}
        old_key=old.get("committed_state_key") or old.get("state_key")
        same_rule=old.get("rule_hash")==row["rule_hash"] if old else False
        baseline_only=(not old) or (not same_rule) or starting_forward
        switches=per_playbook.get(row["playbook_id"]) or {"enabled":True,"ledger_enabled":True,"notifications_enabled":False}
        runtime_active=bool(switches.get("enabled") and switches.get("ledger_enabled"))
        row["runtime"]={**switches,"ledger_active":bool(forward_active and runtime_active)}
        row["continuity"]=_continuity_meta(old,row)
        row.update({
            "last_valid_state_key":row["continuity"].get("last_valid_state_key"),
            "last_valid_market_date":row["continuity"].get("last_valid_market_date"),
            "unknown_since_market_date":row["continuity"].get("unknown_since_market_date"),
            "late_detected":row["continuity"].get("late_detected",False),
            "detection_delay_sessions":row["continuity"].get("detection_delay_sessions",0),
            "timing_uncertain":row["continuity"].get("timing_uncertain",False),
        })
        row["previous_state_key"]=old_key
        row["transition_detected"]=False
        row["suppressed_by_kill_switch"]=False
        row["bootstrap"]=baseline_only
        if baseline_only:
            if forward_active and runtime_active:
                audit_events.append(_audit_event("state_baseline",f'{row["entity_key"]} baseline {row["state_key"]}',gate["market_date"],now,commit_sha,{"entity_key":row["entity_key"],"rule_hash":row["rule_hash"]}))
            continue
        if row["state_key"]==old_key:
            continue
        row["transition_detected"]=True
        if not forward_active:
            continue
        if not runtime_active:
            row["suppressed_by_kill_switch"]=True
            audit_events.append(_audit_event(
                "transition_suppressed_by_kill_switch",
                f'{row["entity_key"]} transition {old_key} -> {row["state_key"]} suppressed while playbook runtime/ledger is paused.',
                gate["market_date"],now,commit_sha,
                {"entity_key":row["entity_key"],"playbook_id":row["playbook_id"],"rule_hash":row["rule_hash"],"scoreable":False}
            ))
            continue
        if row["state"]=="UNDETERMINED":
            ev=_audit_event("undetermined",f'{row["entity_key"]}: {row["detail"]}',gate["market_date"],now,commit_sha,{
                "entity_key":row["entity_key"],"rule_hash":row["rule_hash"],
                "last_valid_market_date":row["continuity"].get("last_valid_market_date"),
                "unknown_since_market_date":row["continuity"].get("unknown_since_market_date"),
                "scoreable":False,
            })
            audit_events.append(ev);pending_by_entity[row["entity_key"]]=ev["record_id"]
        elif row["state"]=="NO_CHASE":
            ev=_event(row,old_key,now,commit_sha,"discipline_event")
            discipline_events.append(ev);pending_by_entity[row["entity_key"]]=ev["record_id"]
        else:
            ev=_event(row,old_key,now,commit_sha,"trigger_state_event")
            trigger_events.append(ev);pending_by_entity[row["entity_key"]]=ev["record_id"]
            if row["continuity"].get("late_detected"):
                audit_events.append(_audit_event(
                    "late_detection_window",
                    f'{row["entity_key"]} was detected after one or more unobserved/invalid sessions; exact transition date is unknown.',
                    gate["market_date"],now,commit_sha,{
                        "entity_key":row["entity_key"],
                        "playbook_id":row["playbook_id"],
                        "detection_delay_sessions":row["continuity"].get("detection_delay_sessions"),
                        "detection_window_start":row["continuity"].get("detection_window_start"),
                        "detection_window_end":row["continuity"].get("detection_window_end"),
                        "timing_uncertain":True,
                        "scoreable":False,
                    }
                ))
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
            stream_events={"trigger":trigger_events,"audit":audit_events,"discipline":discipline_events,"correction":correction_events}
            for stream in ("trigger","audit","discipline","correction"):
                res=writer.append_many(stream,stream_events[stream],gate["market_date"] or now.date().isoformat())
                results.append(res)
                if res.reconciled and stream!="correction":
                    corr=_audit_event(
                        "ledger_head_reconciled",
                        f"{stream} ledger monthly file verified ahead of stale head metadata; head metadata repaired.",
                        gate["market_date"],now,commit_sha,
                        {"stream":stream,"recovered_records":res.recovered_records,"semantic_change":False}
                    )
                    corr["record_type"]="correction_event"
                    correction_events.append(corr)
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

    observed=parse_date(gate.get("market_date"))
    baseline=parse_date(FORWARD_BASELINE_DATE)
    stabilization_completed=0
    if observed and baseline and observed>=baseline:
        stabilization_completed=min(STABILIZATION_SESSIONS,1+len(sessions_between(baseline,observed)))
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
            "per_playbook":per_playbook,
            "operator_controls":"repository_variables",
        },
        "storage":{
            "configured":storage_configured,
            "configured_repo":configured_repo,
            "token_present":token_present,
            "reason":storage_reason,
            "forward_clock_active":forward_active,
            "health":anchor["status"],
            "raw_private":True,
            "public_output":"sanitized status + anchor only",
        },
        "stabilization":{
            "start_market_date":FORWARD_BASELINE_DATE,
            "completed_sessions":stabilization_completed,
            "target_sessions":STABILIZATION_SESSIONS,
            "complete":stabilization_completed>=STABILIZATION_SESSIONS,
        },
        "counts":{
            "entities":len(rows),
            "triggered":sum(1 for x in rows if x["state"]=="TRIGGERED"),
            "near_trigger":sum(1 for x in rows if x["state"]=="NEAR_TRIGGER"),
            "undetermined":sum(1 for x in rows if x["state"]=="UNDETERMINED"),
            "transitions":sum(1 for x in rows if x["transition_detected"]),
            "private_trigger_events_pending":len(trigger_events),
            "late_detected_entities":sum(1 for x in rows if x.get("late_detected")),
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
