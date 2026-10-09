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


SERVER_MAX_AGE_MIN = 75
SERVER_MARK = "server-guardian"


def us_session_open(now_utc: datetime) -> bool:
    local = now_utc.astimezone(ET)
    return tc.is_session(local.date()) and time(9, 30) <= local.time() <= time(16, 15)


def decide_server(now_utc: datetime, generated_at: str | None, runs: list[dict]) -> dict:
    """Server Action Watch freshness during the US session (its cron is heavily throttled).
    At most one guard dispatch per clock hour; never while a run is queued/in progress."""
    if not us_session_open(now_utc):
        return {"action": "ok", "reason": "outside_us_session"}
    # server_action_status.json is only rewritten when its content changes (or every 6 h), so its
    # generated_at is not a liveness signal on its own. The last *successful* Server Action Watch run
    # (GitHub's own clock) proves the server checked; use whichever is newer.
    stamps = [generated_at] + [r.get("updated_at") or r.get("created_at") for r in runs
                               if r.get("status") == "completed" and r.get("conclusion") == "success"]
    ages = []
    for t in stamps:
        try:
            ages.append((now_utc - datetime.fromisoformat(str(t).replace("Z", "+00:00"))).total_seconds() / 60)
        except Exception:
            pass
    age = min(ages) if ages else None
    if age is not None and age <= SERVER_MAX_AGE_MIN:
        return {"action": "ok", "age_min": round(age)}
    if any(r.get("status") in ("queued", "in_progress", "waiting", "pending", "requested") for r in runs):
        return {"action": "wait", "reason": "server_watch_running"}
    hour = now_utc.strftime("%Y-%m-%dT%H")
    if any(SERVER_MARK in str(r.get("display_title") or "") and str(r.get("created_at") or "").startswith(hour) for r in runs):
        return {"action": "wait", "reason": "already_dispatched_this_hour"}
    return {"action": "dispatch", "age_min": None if age is None else round(age)}


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
    inject = os.getenv("GUARD_INJECT_MARKET_AS_OF")  # fault injection: evaluate as if data were stale (dry run only)
    if inject:
        os.environ["GUARD_DRY_RUN"] = "1"
        data = {"trend_pulse": {"X": {"available": True, "date": inject}}}
        print(f"::notice title=Daily guardian::FAULT_INJECTION market_as_of={inject} (dry run, no dispatch)")
    # Guard-dispatched runs carry the guard marker in their run-name (daily.yml run-name uses inputs.run_reason).
    d = decide(datetime.now(timezone.utc), published_market_as_of(data), runs)
    print(f"::notice title=Daily guardian::DAILY_GUARD {json.dumps(d, sort_keys=True)}")
    if d["action"] == "dispatch" and os.getenv("GUARD_DRY_RUN") != "1":
        gh("POST", "actions/workflows/daily.yml/dispatches", {"ref": "main", "inputs": {"run_reason": f"{GUARD_MARK} {d['expected']} #{d['attempt']}"}})
        print(f"::warning title=Daily guardian::DAILY_MISSED dispatched Daily for {d['expected']} (attempt {d['attempt']}/{MAX_DISPATCH})")
    elif d["action"] == "give_up":
        print(f"::error title=Daily guardian::DAILY_STILL_STALE {d['expected']} after {MAX_DISPATCH} guard dispatches; explicit GAP, no backfill")
    srv = json.loads((ROOT / "docs" / "research" / "server_action_status.json").read_text(encoding="utf-8"))
    sruns = (gh("GET", "actions/workflows/server-action-watch.yml/runs?per_page=20") or {}).get("workflow_runs", [])
    sd = decide_server(datetime.now(timezone.utc), srv.get("generated_at"), sruns)
    print(f"::notice title=Daily guardian::SERVER_GUARD {json.dumps(sd, sort_keys=True)}")
    if sd["action"] == "dispatch" and os.getenv("GUARD_DRY_RUN") != "1":
        gh("POST", "actions/workflows/server-action-watch.yml/dispatches", {"ref": "main", "inputs": {"run_reason": f"{SERVER_MARK} {datetime.now(timezone.utc):%Y-%m-%dT%H}"}})
        print(f"::warning title=Daily guardian::SERVER_WATCH_STALE dispatched Server Action Watch (age {sd.get('age_min')} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
