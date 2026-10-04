#!/usr/bin/env python3
"""Independent Playbook watchdog.

Fails loudly when the published Forward status is missing, behind the latest
completed US session, or reports an unhealthy private-ledger bridge. It does
not mutate Playbook rules or ledger records.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from trading_calendar import expected_latest_completed_session

ROOT=Path(__file__).resolve().parents[1]
STATUS=ROOT/"docs"/"research"/"playbook_status.json"
ANCHOR=ROOT/"docs"/"research"/"ledger_anchor.json"
FAILURES=ROOT/"docs"/"research"/"module_failures.json"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def parse_iso(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None

def check(now=None):
    now=now or datetime.now(timezone.utc)
    s=load(STATUS);a=load(ANCHOR);f=load(FAILURES)
    expected=expected_latest_completed_session(now).isoformat()
    problems=[]
    if not s:problems.append("missing_playbook_status")
    market=str(s.get("market_date") or "")[:10]
    if market!=expected:problems.append(f"market_date_stale:{market or 'missing'}!=expected:{expected}")
    if (s.get("heartbeat") or {}).get("status")!="pass":problems.append("heartbeat_not_pass")
    if (s.get("storage") or {}).get("forward_clock_active") and a.get("status")!="ok":
        problems.append(f"ledger_anchor_{a.get('status') or 'missing'}")
    generated=parse_iso(s.get("generated_at"))
    failure=(f.get("modules") or {}).get("playbook_engine") or {}
    failed_at=parse_iso(failure.get("failed_at"))
    if failed_at and (not generated or failed_at>generated):
        problems.append("isolated_playbook_failure_newer_than_status")
    return {
        "ok":not problems,
        "checked_at":now.isoformat(),
        "expected_market_date":expected,
        "observed_market_date":market or None,
        "problems":problems,
    }

def main():
    result=check()
    print(json.dumps(result,ensure_ascii=False))
    if not result["ok"]:raise SystemExit(1)

if __name__=="__main__":
    main()
