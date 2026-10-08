#!/usr/bin/env python3
"""Append-only operational incident -> remediation memory.

Consumes the public/sanitized System Status snapshot only. It records incident
state transitions, not secrets or raw logs. Research/operations governance only.
"""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATUS=ROOT/"docs"/"research"/"system_status.json"
STATE=ROOT/"research"/"store"/"operational_incident_state.json"
ARCH=ROOT/"research"/"archive"/"operational_incidents.jsonl"
OUT=ROOT/"docs"/"research"/"operational_incident_memory.json"

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def issue_key(kind,scope,name,reason):
    raw="|".join([kind,scope,name,reason])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

def current_issues(status):
    out={}
    for repo,flows in (status.get("workflows") or {}).items():
        for name,row in (flows or {}).items():
            health=row.get("health")
            if health!="bad":continue
            reason=str(row.get("conclusion") or row.get("status") or "bad")
            key=issue_key("workflow",repo,name,reason)
            out[key]={
              "issue_key":key,"kind":"workflow","scope":repo,"name":name,
              "reason":reason,"first_snapshot_at":status.get("generated_at"),
              "evidence":{"status":row.get("status"),"conclusion":row.get("conclusion"),"head_sha":row.get("head_sha"),"updated_at":row.get("updated_at")},
            }
    for name,row in (status.get("artifacts") or {}).items():
        freshness=row.get("freshness")
        business=row.get("business_freshness")
        if freshness not in {"stale","missing"} and business!="stale":continue
        reason="business_stale" if business=="stale" else str(freshness)
        key=issue_key("artifact","quant-dashboard",name,reason)
        out[key]={
          "issue_key":key,"kind":"artifact","scope":"quant-dashboard","name":name,
          "reason":reason,"first_snapshot_at":status.get("generated_at"),
          "evidence":{"freshness":freshness,"business_freshness":business,"market_as_of":row.get("market_as_of"),"expected_market_date":row.get("expected_market_date"),"updated_at":row.get("updated_at")},
        }
    return out

def append_event(row):
    ARCH.parent.mkdir(parents=True,exist_ok=True)
    with ARCH.open("a",encoding="utf-8") as f:
        f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")

def run(status=None,now=None):
    status=status or load(STATUS,{})
    now=now or datetime.now(timezone.utc).isoformat()
    prior=load(STATE,{"version":1,"open":{},"resolved_count":0})
    previous=dict(prior.get("open") or {})
    current=current_issues(status)
    opened=[];resolved=[]
    for key,row in current.items():
        if key in previous:continue
        event={**row,"event":"opened","event_at":now,"production_effect":"none"}
        append_event(event);opened.append(event)
    for key,row in previous.items():
        if key in current:continue
        event={
          "issue_key":key,"kind":row.get("kind"),"scope":row.get("scope"),"name":row.get("name"),
          "reason":row.get("reason"),"event":"resolved","event_at":now,
          "opened_at":row.get("opened_at") or row.get("first_snapshot_at"),
          "resolution_evidence":{"system_status_generated_at":status.get("generated_at")},
          "production_effect":"none",
        }
        append_event(event);resolved.append(event)
    open_state={}
    for key,row in current.items():
        old=previous.get(key) or {}
        open_state[key]={
          **row,
          "opened_at":old.get("opened_at") or now,
          "last_seen_at":now,
        }
    state={
      "version":1,"updated_at":now,"open":open_state,
      "resolved_count":int(prior.get("resolved_count") or 0)+len(resolved),
    }
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary={
      "version":1,"generated_at":now,"status":"learning_active",
      "counts":{"open":len(open_state),"opened_this_run":len(opened),"resolved_this_run":len(resolved),"resolved_total":state["resolved_count"]},
      "open_incidents":list(open_state.values()),
      "guardrails":[
        "Incident memory stores sanitized workflow/artifact states only; no secrets or private ledger data.",
        "A red status is never auto-suppressed. Resolution requires disappearance from a later System Status snapshot.",
        "Operational learning may change attention/diagnostics, never protected Production trading rules."
      ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False))
