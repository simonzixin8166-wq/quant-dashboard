"""Monitors accept "Daily pending" only inside the post-close grace window (2026-10-22/23 nightly false reds:
Playbook watchdog 63/67 and Autonomous QA 1162/1163 ran after the close but before Daily published).
Production engines keep the strict expected session; the window closes at close + 5h."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc
import playbook_watchdog as wd

Z = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

# grace window: Fri 2026-10-23 close 16:15 ET (20:15Z) .. 21:15 ET (01:15Z Sat)
assert tc.monitor_grace_session(Z("2026-10-23T19:00:00")) is None            # before close: strict = 10-22 anyway
assert str(tc.monitor_grace_session(Z("2026-10-23T21:05:00"))) == "2026-10-22"  # QA 1162 / watchdog 67 time
assert str(tc.monitor_grace_session(Z("2026-10-24T00:04:00"))) == "2026-10-22"  # QA 1163 time (race)
assert tc.monitor_grace_session(Z("2026-10-24T01:20:00")) is None            # window over: strict only
assert tc.monitor_grace_session(Z("2026-10-24T12:00:00")) is None            # Saturday
assert tc.monitor_grace_session(Z("2026-10-26T14:00:00")) is None            # Monday before close
assert str(tc.expected_latest_completed_session(Z("2026-10-23T21:05:00"))) == "2026-10-23"  # strict unchanged
assert tc.MONITOR_GRACE_HOURS == 5

# watchdog
old = (wd.STATUS, wd.ANCHOR, wd.FAILURES)
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    wd.STATUS, wd.ANCHOR, wd.FAILURES = d / "s.json", d / "a.json", d / "f.json"
    wd.ANCHOR.write_text(json.dumps({"status": "ok"}))
    wd.FAILURES.write_text(json.dumps({"modules": {}}))
    put = lambda m: wd.STATUS.write_text(json.dumps({"market_date": m, "generated_at": "2026-10-23T00:10:00+00:00",
                                                     "heartbeat": {"status": "pass"}, "storage": {"forward_clock_active": True}}))
    put("2026-10-22")
    r = wd.check(Z("2026-10-23T21:27:00"))
    assert r["ok"] and r["pending_daily"] is True, r                     # was the nightly false red
    r = wd.check(Z("2026-10-24T01:30:00"))
    assert not r["ok"] and r["problems"] == ["market_date_stale:2026-10-22!=expected:2026-10-23"], r  # Daily missed
    put("2026-10-21")
    assert not wd.check(Z("2026-10-23T21:27:00"))["ok"]                  # two sessions behind is never pending
    put("2026-10-23")
    r = wd.check(Z("2026-10-23T21:27:00"))
    assert r["ok"] and r["pending_daily"] is False                       # already published
    put("2026-10-26")
    assert not wd.check(Z("2026-10-24T12:00:00"))["ok"]                  # a future date still fails
wd.STATUS, wd.ANCHOR, wd.FAILURES = old

# QA: strict date and fail-closed server rule kept; grace only via the calendar's --grace output
qa = (ROOT / "scripts" / "autonomous_site_qa.mjs").read_text(encoding="utf-8")
assert "marketAsOf===expected" in qa and "serverMarketAsOf===expected" in qa and "&&serverCurrent" in qa
assert "process.env.EXPECTED_MARKET_DATE_GRACE" in qa and "QA_PENDING_DAILY" in qa
assert "==='cannot_judge'&&String(server?.judgment_basis||'')==='market_data_stale'" in qa
assert "pendingDaily=Boolean(graceDate)&&marketAsOf===graceDate" in qa
wf = (ROOT / ".github" / "workflows" / "autonomous-qa.yml").read_text(encoding="utf-8")
assert 'EXPECTED_MARKET_DATE_GRACE=$(python scripts/trading_calendar.py --grace)' in wf
# production engines never use the monitor grace
for f in ("server_action_engine.py", "daily_guardian.py", "system_status_center.py", "playbook_engine.py"):
    assert "monitor_grace_session" not in (ROOT / "scripts" / f).read_text(encoding="utf-8"), f
print("PASS monitor close grace: watchdog/QA accept 'Daily pending' only until close+5h; engines stay strict")
