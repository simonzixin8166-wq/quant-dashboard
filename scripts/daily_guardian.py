#!/usr/bin/env python3
"""Independent health guard for missed Daily runs (GitHub cron can be delayed or skipped).

Decision is a pure function (decide) so it is unit-tested; main() only gathers inputs from
docs/data.json and the Actions REST API and, when told to, dispatches daily.yml once.

Rules (no loops, idempotent):
- ok        : published market_as_of >= expected latest completed NYSE session.
- wait      : a Daily run is queued / in progress, or the session closed < GRACE minutes ago.
- dispatch  : stale, nothing running, and the guard has dispatched < MAX_DISPATCH times for this session.
- give_up   : stale after MAX_DISPATCH guard dispatches → error annotation, no further dispatch
              (the gap stays explicit in forward_observation_status; nothing is backfilled), plus ONE
              Telegram alert per session (owner decision #133 6184936851: alerts replace Claude check-ins).
"""
from __future__ import annotations
import json, os, sys, time as _time, urllib.request
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


def should_alert_give_up(d: dict, daily_runs: list[dict], guardian_runs: list[dict], current_run_id=None) -> bool:
    """One alert per session, stateless: only the first guardian run after the last guard-dispatched Daily
    for this session finished alerts; later guardian runs see an earlier sibling and stay silent."""
    if d.get("action") != "give_up":
        return False
    mark = f"{GUARD_MARK} {d.get('expected')}"
    guard = [r for r in daily_runs if r.get("event") == "workflow_dispatch" and mark in str(r.get("display_title") or "")]
    if not guard:
        return False
    done = max(str(r.get("updated_at") or r.get("created_at") or "") for r in guard)
    earlier = [r for r in guardian_runs if str(r.get("id")) != str(current_run_id) and str(r.get("created_at") or "") > done]
    return not earlier


def give_up_message(d: dict) -> str:
    return ("MyAlpha 告警：Daily 数据仍未更新\n"
            f"- 预期交易日：{d.get('expected')}；已发布 market_as_of：{d.get('market_as_of')}\n"
            f"- Guardian 已补发 {MAX_DISPATCH} 次仍无新数据，停止自动补发（显式 GAP，不回填）\n"
            "- 需要人工查看 Actions：Daily Dashboard Update")


def send_telegram(text: str) -> str:
    token, chat = os.getenv("MYALPHA_TG_BOT_TOKEN"), os.getenv("MYALPHA_TG_CHAT_ID")
    if not token or not chat:
        return "not_configured"
    import urllib.parse
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                                           data=body, method="POST"), timeout=12) as r:
            r.read()
    except Exception as exc:
        return f"failed:{type(exc).__name__}"
    return "sent"


SERVER_MAX_AGE_MIN = 75
SERVER_MARK = "server-guardian"
# A guard-dispatched Daily is created by GITHUB_TOKEN, so its completion fires no workflow_run and Server Action
# Watch (which reacts to Daily) never runs; the guardian's own catch-up crons are throttled (10/28: 23:47 -> 01:17Z
# with the server snapshot on the previous session). The guardian therefore follows its own dispatch to the end
# and then refreshes Server Action Watch itself (Owner-approved option B, 10/29). No permission change.
FOLLOW_MAX_MIN = int(os.getenv("GUARD_FOLLOW_MAX_MIN", "25"))
FOLLOW_POLL_SEC = int(os.getenv("GUARD_FOLLOW_POLL_SEC", "60"))
_ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")


def follow_dispatched(run_reason: str, list_runs, sleep=_time.sleep, clock=_time.monotonic,
                      max_min: int = FOLLOW_MAX_MIN, poll_sec: int = FOLLOW_POLL_SEC) -> dict:
    """Wait for the Daily run whose run-name carries run_reason. Returns
    {"result": "success"} when it completed successfully, else "failed" / "timeout" (no refresh then:
    the normal alerts and the throttled catch-up crons stay the fallback)."""
    start = clock()
    while True:
        try:
            runs = list_runs() or []
        except Exception as exc:  # transient API error: keep waiting within the budget
            runs = []
            print(f"::notice title=Daily guardian::FOLLOW list error {type(exc).__name__}")
        mine = [r for r in runs if run_reason in str(r.get("display_title") or "")]
        if mine:
            r = max(mine, key=lambda x: str(x.get("created_at") or ""))
            if r.get("status") == "completed":
                ok = r.get("conclusion") == "success"
                return {"result": "success" if ok else "failed", "run_id": r.get("id"), "conclusion": r.get("conclusion")}
        if clock() - start >= max_min * 60:
            return {"result": "timeout", "run_id": mine and mine[0].get("id")}
        sleep(poll_sec)


def us_session_open(now_utc: datetime) -> bool:
    local = now_utc.astimezone(ET)
    return tc.is_session(local.date()) and time(9, 30) <= local.time() <= time(16, 15)


def _hour_guard(now_utc, runs):
    if any(r.get("status") in ("queued", "in_progress", "waiting", "pending", "requested") for r in runs):
        return {"action": "wait", "reason": "server_watch_running"}
    hour = now_utc.strftime("%Y-%m-%dT%H")
    if any(SERVER_MARK in str(r.get("display_title") or "") and str(r.get("created_at") or "").startswith(hour) for r in runs):
        return {"action": "wait", "reason": "already_dispatched_this_hour"}
    return None


def decide_server(now_utc: datetime, generated_at: str | None, runs: list[dict],
                  server_market_as_of: str | None = None, published_market_as_of: str | None = None) -> dict:
    """Server Action Watch freshness (its cron is heavily throttled).
    - any time: the server snapshot lags the published market date (e.g. a guardian-dispatched Daily,
      whose completion does not fire workflow_run, so the server chain never ran) → dispatch;
    - US session: no successful run / status refresh for > SERVER_MAX_AGE_MIN → dispatch.
    At most one guard dispatch per clock hour; never while a run is queued/in progress."""
    if server_market_as_of and published_market_as_of and str(server_market_as_of) < str(published_market_as_of):
        g = _hour_guard(now_utc, runs)
        return g or {"action": "dispatch", "reason": "server_snapshot_behind_market",
                     "server_market_as_of": server_market_as_of, "market_as_of": published_market_as_of}
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
    g = _hour_guard(now_utc, runs)
    return g or {"action": "dispatch", "age_min": None if age is None else round(age)}


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
    refreshed = False
    d = decide(datetime.now(timezone.utc), published_market_as_of(data), runs)
    print(f"::notice title=Daily guardian::DAILY_GUARD {json.dumps(d, sort_keys=True)}")
    if d["action"] == "dispatch" and os.getenv("GUARD_DRY_RUN") != "1":
        reason = f"{GUARD_MARK} {d['expected']} #{d['attempt']}"
        gh("POST", "actions/workflows/daily.yml/dispatches", {"ref": "main", "inputs": {"run_reason": reason}})
        print(f"::warning title=Daily guardian::DAILY_MISSED dispatched Daily for {d['expected']} (attempt {d['attempt']}/{MAX_DISPATCH})")
        f = follow_dispatched(reason, lambda: (gh("GET", "actions/workflows/daily.yml/runs?event=workflow_dispatch&per_page=10") or {}).get("workflow_runs", []))
        print(f"::notice title=Daily guardian::FOLLOW_DAILY {json.dumps(f, sort_keys=True)}")
        if f["result"] == "success":
            gh("POST", "actions/workflows/server-action-watch.yml/dispatches",
               {"ref": "main", "inputs": {"run_reason": f"{SERVER_MARK} after-daily {d['expected']}"}})
            print(f"::warning title=Daily guardian::SERVER_REFRESH_AFTER_DAILY dispatched Server Action Watch for {d['expected']}")
            refreshed = True
    elif d["action"] == "give_up":
        print(f"::error title=Daily guardian::DAILY_STILL_STALE {d['expected']} after {MAX_DISPATCH} guard dispatches; explicit GAP, no backfill")
        try:
            gruns = (gh("GET", "actions/workflows/daily-guardian.yml/runs?per_page=30") or {}).get("workflow_runs", [])
        except Exception as exc:  # never let the alert path break the guardian / server check below
            gruns = None
            print(f"::warning title=Daily guardian::GIVE_UP_ALERT skipped (guardian runs unavailable: {type(exc).__name__})")
        if gruns is None:
            pass
        elif should_alert_give_up(d, runs, gruns, os.getenv("GITHUB_RUN_ID")):
            status = "dry_run" if os.getenv("GUARD_DRY_RUN") == "1" else send_telegram(give_up_message(d))
            print(f"::warning title=Daily guardian::GIVE_UP_ALERT {status}")
        else:
            print("::notice title=Daily guardian::GIVE_UP_ALERT already_sent_this_session")
    if refreshed:  # the checkout predates the Daily it just followed; the refresh above already covers the server
        print("::notice title=Daily guardian::SERVER_GUARD skipped (refreshed after the followed Daily)")
        return 0
    srv = json.loads((ROOT / "docs" / "research" / "server_action_status.json").read_text(encoding="utf-8"))
    sruns = (gh("GET", "actions/workflows/server-action-watch.yml/runs?per_page=20") or {}).get("workflow_runs", [])
    sd = decide_server(datetime.now(timezone.utc), srv.get("generated_at"), sruns,
                       (srv.get("data_trust") or {}).get("market_as_of"), published_market_as_of(data))
    print(f"::notice title=Daily guardian::SERVER_GUARD {json.dumps(sd, sort_keys=True)}")
    if sd["action"] == "dispatch" and os.getenv("GUARD_DRY_RUN") != "1":
        gh("POST", "actions/workflows/server-action-watch.yml/dispatches", {"ref": "main", "inputs": {"run_reason": f"{SERVER_MARK} {datetime.now(timezone.utc):%Y-%m-%dT%H}"}})
        print(f"::warning title=Daily guardian::SERVER_WATCH_STALE dispatched Server Action Watch (age {sd.get('age_min')} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
