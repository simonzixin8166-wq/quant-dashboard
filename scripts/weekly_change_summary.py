#!/usr/bin/env python3
"""Weekly change summary (owner decision #133 6184936851): one compact, fixed-field JSON per week,
written ONLY when a tracked field changed versus the previous summary; otherwise nothing is written
and nothing is sent. Replaces recurring long Claude reports. Read-only over existing artifacts plus the
Actions REST API; no model calls, no paid service.

Fields (missing evidence → "unavailable", never a default):
  schedule        Daily 21:30Z event=schedule per NYSE session in the last 7 days (owner rule 2026-10-17):
                  on_time = the slot's schedule run succeeded and finished before the next NYSE session's
                  09:30 ET open; degraded = succeeded but finished after that open; gap = failed / none.
                  A run is attributed to the 21:30Z slot only if created before the next weekday 08:15Z
                  cron (the A/H-share snapshot slot). Guardian recoveries are counted separately and never
                  as on-time.
  ohlcv_40        archive symbols whose last bar ≥ the expected session (docs/research/historical_journal.json).
  forward_mature  matured forward samples (docs/research/learning_quality_weekly.json snapshot).
  open_incidents  unresolved operational incidents (docs/research/operational_incident_memory.json).
"""
from __future__ import annotations
import json, os, sys, urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

OUT = ROOT / "docs" / "research" / "weekly_change_summary.json"
ET = ZoneInfo("America/New_York")
NEXT_SLOT = time(8, 15)  # the other Daily cron (weekdays 08:15Z)
GUARD_MARK = "daily-guardian"


def _t(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _next_weekday(d: date) -> date:
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return n


def schedule_week(runs: list[dict], today: date) -> dict:
    sessions = [today - timedelta(days=i) for i in range(1, 8)]
    sessions = sorted(d for d in sessions if tc.is_session(d))
    rows, counts = [], {"on_time": 0, "degraded": 0, "gap": 0}
    for d in sessions:
        cron = datetime.combine(d, time(21, 30), timezone.utc)
        until = datetime.combine(_next_weekday(d), NEXT_SLOT, timezone.utc)
        next_open = datetime.combine(tc.next_session(d), time(9, 30), ET).astimezone(timezone.utc)
        sched = sorted((r for r in runs if r.get("event") == "schedule" and cron <= _t(r["created_at"]) < until),
                       key=lambda r: r["created_at"])
        rec = [r for r in runs if r.get("event") == "workflow_dispatch" and GUARD_MARK in str(r.get("display_title") or "")
               and d.isoformat() in str(r.get("display_title") or "")]
        if sched:
            r0 = sched[0]
            delay = round((_t(r0["created_at"]) - cron).total_seconds() / 60)
            finished = _t(r0.get("updated_at") or r0["created_at"])
            ok = r0.get("conclusion") == "success"
            verdict = "on_time" if ok and finished < next_open else "degraded" if ok else "gap"
        else:
            delay, verdict = None, "gap"
        counts[verdict] += 1
        rows.append({"session": d.isoformat(), "schedule_run_id": sched[0]["id"] if sched else None,
                     "delay_min": delay, "next_open_utc": next_open.isoformat().replace("+00:00", "Z"),
                     "verdict": verdict, "guardian_recoveries": len(rec)})
    return {"sessions": len(sessions), **counts, "rows": rows,
            "rule": "event=schedule only; on_time = success finished before next NYSE 09:30 ET open "
                    "(owner #133 2026-10-17); degraded = success after that open; recovery never counts"}


def ohlcv_40(journal: dict) -> dict:
    exp = (journal.get("update") or {}).get("expected_session")
    cov = [c for c in journal.get("coverage") or [] if c.get("symbol") != "VIX"]
    if not exp or not cov:
        return {"status": "unavailable"}
    complete = [c["symbol"] for c in cov if str(c.get("last_date")) >= exp]
    return {"expected_session": exp, "complete": len(complete), "universe": len(cov),
            "stale": sorted(c["symbol"] for c in cov if str(c.get("last_date")) < exp)}


def forward_mature(lq: dict) -> dict:
    snap = lq.get("snapshot") or {}
    if not snap:
        return {"status": "unavailable"}
    n = lambda e, k: ((snap.get(e) or {}).get("numeric") or {}).get(k)
    return {"market_forward_20": n("market", "forward_mature_20"), "market_forward_60": n("market", "forward_mature_60"),
            "options_mature": n("options", "mature_outcomes"), "fundamental_outcome_20": n("fundamental", "outcome_mature_20"),
            "learning": "UNPROVEN / FINAL=NO"}


def build(runs, today, journal, lq, incidents) -> dict:
    return {"schedule_7d": schedule_week(runs, today) if runs is not None else {"status": "unavailable"}, "ohlcv_40": ohlcv_40(journal),
            "forward_mature": forward_mature(lq),
            "open_incidents": (incidents.get("counts") or {}).get("open", "unavailable") if incidents else "unavailable"}


def changed(new: dict, old: dict | None) -> bool:
    return not old or old.get("fields") != new


def message(f: dict) -> str:
    s, o, m = f["schedule_7d"], f["ohlcv_40"], f["forward_mature"]
    sched = (f"{s['on_time']}/{s['sessions']}，DEGRADED {s['degraded']}，GAP {s['gap']}" if "sessions" in s else "unavailable")
    return ("MyAlpha 每周变化摘要\n"
            f"- Daily 准点（schedule）：{sched}\n"
            f"- 40 标的完整：{o.get('complete', '?')}/{o.get('universe', '?')}（{o.get('expected_session', 'unavailable')}）\n"
            f"- 前向成熟样本：市场20日 {m.get('market_forward_20')}，期权 {m.get('options_mature')}；Learning UNPROVEN\n"
            f"- 未解决事件：{f['open_incidents']}")


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def _runs():
    tok, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not tok or not repo:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/daily.yml/runs?per_page=100",
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "MyAlpha-Weekly-Summary"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode()).get("workflow_runs", [])
    except Exception as exc:
        print(f"::warning title=Weekly change summary::Actions runs unavailable ({type(exc).__name__})")
        return None


def main() -> int:
    now = datetime.now(timezone.utc)
    fields = build(_runs(), now.date(), _load(ROOT / "docs/research/historical_journal.json") or {},
                   _load(ROOT / "docs/research/learning_quality_weekly.json") or {},
                   _load(ROOT / "docs/research/operational_incident_memory.json"))
    if not changed(fields, _load(OUT)):
        print("::notice title=Weekly change summary::NO_CHANGE (nothing written, nothing sent)")
        return 0
    OUT.write_text(json.dumps({"version": 1, "generated_at": now.isoformat(timespec="seconds"), "fields": fields},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    sys.path.insert(0, str(ROOT / "scripts"))
    from daily_guardian import send_telegram  # same MYALPHA_TG_* sender, no new service
    print(f"::notice title=Weekly change summary::CHANGED telegram={send_telegram(message(fields))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
