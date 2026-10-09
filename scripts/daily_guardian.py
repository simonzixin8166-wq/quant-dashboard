#!/usr/bin/env python3
"""Independent health guard for missed Daily runs (GitHub cron can be delayed or skipped).

Decision is a pure function (decide) so it is unit-tested; main() only gathers inputs from
docs/data.json and the Actions REST API and, when told to, dispatches daily.yml once.

Rules (no loops, idempotent):
- ok        : published market_as_of >= expected latest completed NYSE session.
- wait      : a Daily run is queued / in progress, or the session closed < GRACE minutes ago.
- dispatch  : stale, nothing running, and the guard has dispatched < MAX_DISPATCH times for this session.
- give_up   : stale after MAX_DISPATCH guard dispatches → warning annotation, no further dispatch
              (the gap stays explicit in forward_observation_status; nothing is backfilled).
"""
from __future__ import annotations
import json, os, sys, urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

ET = ZoneInfo("America/New_York")
MAX_DISPATCH = 2
GRACE_MIN = 90          # cron is 21:30 UTC ≈ 75 min after 16:15 ET; give it time first
GUARD_MARK = "daily-guardian"


def published_market_as_of(data: dict) -> str | None:
    tp = data.get("trend_pulse") or {}
    dates = sorted(str(v.get("date"))[:10] for v in tp.values() if isinstance(v, dict) and v.get("available") and v.get("date"))
    if dates:
        return dates[-1]
    idx = (data.get("index") or {}).get("QQQ") or {}
    return str(idx.get("date"))[:10] if idx.get("date") else None


def session_close_utc(session: date) -> datetime:
    return datetime.combine(session, time(16, 15), ET).astimezone(timezone.utc)


def decide(now_utc: datetime, market_as_of: str | None, runs: list[dict]) -> dict:
    expected = tc.expected_latest_completed_session(now_utc)
    if market_as_of and market_as_of >= expected.isoformat():
        return {"action": "ok", "expected": expected.isoformat(), "market_as_of": market_as_of}
    closed = session_close_utc(expected)
    base = {"expected": expected.isoformat(), "market_as_of": market_as_of}
    if now_utc < closed + timedelta(minutes=GRACE_MIN):
        return {"action": "wait", "reason": "grace_period", **base}
    since = [r for r in runs if (r.get("created_at") or "") >= closed.isoformat().replace("+00:00", "Z")]
    if any(r.get("status") in ("queued", "in_progress", "waiting", "pending", "requested") for r in since):
        return {"action": "wait", "reason": "daily_running", **base}
    guard = [r for r in since if r.get("event") == "workflow_dispatch" and GUARD_MARK in str(r.get("display_title") or r.get("actor") or "")]
    if len(guard) >= MAX_DISPATCH:
        return {"action": "give_up", "reason": f"{len(guard)}_guard_dispatches_without_fresh_data", **base}
    return {"action": "dispatch", "reason": "stale_and_idle", "attempt": len(guard) + 1, **base}


def gh(method, path, body=None):
    tok, repo = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "MyAlpha-Daily-Guardian"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else None


def main():
    data = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
    runs = (gh("GET", "actions/workflows/daily.yml/runs?per_page=30") or {}).get("workflow_runs", [])
    # Guard-dispatched runs carry the guard marker in their run-name (daily.yml run-name uses inputs.run_reason).
    d = decide(datetime.now(timezone.utc), published_market_as_of(data), runs)
    print(f"::notice title=Daily guardian::DAILY_GUARD {json.dumps(d, sort_keys=True)}")
    if d["action"] == "dispatch" and os.getenv("GUARD_DRY_RUN") != "1":
        gh("POST", "actions/workflows/daily.yml/dispatches", {"ref": "main", "inputs": {"run_reason": f"{GUARD_MARK} {d['expected']} #{d['attempt']}"}})
        print(f"::warning title=Daily guardian::DAILY_MISSED dispatched Daily for {d['expected']} (attempt {d['attempt']}/{MAX_DISPATCH})")
    elif d["action"] == "give_up":
        print(f"::error title=Daily guardian::DAILY_STILL_STALE {d['expected']} after {MAX_DISPATCH} guard dispatches; explicit GAP, no backfill")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
