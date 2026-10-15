"""Daily guardian: dispatch only when stale and idle, at most twice per session, never loop."""
import importlib.util, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("dg", ROOT / "scripts" / "daily_guardian.py")
dg = importlib.util.module_from_spec(spec); spec.loader.exec_module(dg)

now = datetime(2026, 10, 9, 23, 20, tzinfo=timezone.utc)      # Fri 19:20 ET → expected session 10/09
assert dg.decide(now, "2026-10-09", [])["action"] == "ok"
d = dg.decide(now, "2026-10-08", [])
assert d["action"] == "dispatch" and d["attempt"] == 1 and d["expected"] == "2026-10-09"
# grace period right after close
assert dg.decide(datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc), "2026-10-08", [])["reason"] == "grace_period"
# a Daily already running → wait, never double-dispatch
run = {"created_at": "2026-10-09T23:00:00Z", "status": "in_progress", "event": "schedule", "display_title": "Daily Dashboard Update"}
assert dg.decide(now, "2026-10-08", [run])["reason"] == "daily_running"
# one guard dispatch finished without fresh data → second attempt; two → give up
g = {"created_at": "2026-10-09T23:21:00Z", "status": "completed", "event": "workflow_dispatch", "display_title": "Daily Dashboard Update · daily-guardian 2026-10-09 #1"}
assert dg.decide(now, "2026-10-08", [g])["attempt"] == 2
assert dg.decide(now, "2026-10-08", [g, {**g, "display_title": "Daily Dashboard Update · daily-guardian 2026-10-09 #2"}])["action"] == "give_up"
# manual (non-guard) dispatches and runs before the close do not count toward the guard limit
old = {**g, "created_at": "2026-10-09T10:00:00Z"}
manual = {**g, "display_title": "Daily Dashboard Update"}
assert dg.decide(now, "2026-10-08", [old, old, manual, manual])["action"] == "dispatch"
# weekend: expected session is Friday
sat = datetime(2026, 10, 10, 12, 20, tzinfo=timezone.utc)
assert dg.decide(sat, "2026-10-09", [])["action"] == "ok"
assert dg.published_market_as_of({"trend_pulse": {"A": {"available": True, "date": "2026-10-08"}, "B": {"available": False, "date": "2026-10-09"}}}) == "2026-10-08"
# Server Action Watch freshness during the US session
mid = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)                 # 11:00 ET Fri
assert dg.decide_server(mid, "2026-10-09T14:30:00Z", [])["action"] == "ok"
assert dg.decide_server(mid, "2026-10-09T10:39:00Z", [])["action"] == "dispatch"
assert dg.decide_server(mid, "2026-10-09T10:39:00Z", [{"status": "in_progress"}])["reason"] == "server_watch_running"
assert dg.decide_server(mid, "2026-10-09T10:39:00Z", [{"status": "completed", "display_title": "Server Action Watch · server-guardian 2026-10-09T15", "created_at": "2026-10-09T15:00:05Z"}])["reason"] == "already_dispatched_this_hour"
# unchanged-content file (stale generated_at) but a successful run 30 min ago → fresh, no dispatch
assert dg.decide_server(mid, "2026-10-09T10:39:00Z", [{"status": "completed", "conclusion": "success", "created_at": "2026-10-09T14:58:00Z", "updated_at": "2026-10-09T15:00:00Z"}])["action"] == "ok"
# a failed recent run does not count as liveness
assert dg.decide_server(mid, "2026-10-09T10:39:00Z", [{"status": "completed", "conclusion": "failure", "created_at": "2026-10-09T14:00:00Z"}])["action"] == "dispatch"
assert dg.decide_server(datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc), "2026-10-09T10:39:00Z", [])["action"] == "ok"   # Saturday
assert dg.decide_server(datetime(2026, 10, 9, 22, 0, tzinfo=timezone.utc), None, [])["action"] == "ok"                    # after close
print("PASS daily guardian")

# server chain after a guardian-dispatched Daily: snapshot behind market → dispatch even after hours
night = datetime(2026, 10, 9, 23, 55, tzinfo=timezone.utc)
assert dg.decide_server(night, "2026-10-09T23:04:00Z", [], "2026-10-08", "2026-10-09")["reason"] == "server_snapshot_behind_market"
assert dg.decide_server(night, "2026-10-09T23:04:00Z", [{"status": "in_progress"}], "2026-10-08", "2026-10-09")["reason"] == "server_watch_running"
assert dg.decide_server(night, "2026-10-09T23:04:00Z", [], "2026-10-09", "2026-10-09")["action"] == "ok"
print("PASS server chain")

# give_up → exactly one Telegram alert per session (first guardian run after the 2nd guard Daily finished)
gu = {"action": "give_up", "expected": "2026-10-09", "market_as_of": "2026-10-08"}
g1 = {"event": "workflow_dispatch", "display_title": "Daily Dashboard Update · daily-guardian 2026-10-09 #1", "created_at": "2026-10-09T22:00:00Z", "updated_at": "2026-10-09T22:10:00Z"}
g2 = {**g1, "display_title": "Daily Dashboard Update · daily-guardian 2026-10-09 #2", "created_at": "2026-10-09T23:20:00Z", "updated_at": "2026-10-09T23:31:00Z"}
cur = {"id": 9, "created_at": "2026-10-10T00:40:00Z"}
assert dg.should_alert_give_up(gu, [g1, g2], [cur, {"id": 5, "created_at": "2026-10-09T23:20:00Z"}], 9) is True
assert dg.should_alert_give_up(gu, [g1, g2], [cur, {"id": 8, "created_at": "2026-10-10T00:20:00Z"}], 9) is False   # sibling already alerted
assert dg.should_alert_give_up({**gu, "action": "dispatch"}, [g1, g2], [cur], 9) is False
assert dg.should_alert_give_up({**gu, "expected": "2026-10-12"}, [g1, g2], [cur], 9) is False               # other session's dispatches
msg = dg.give_up_message(gu)
assert "2026-10-09" in msg and "不回填" in msg and "TOKEN" not in msg
import os as _os
_os.environ.pop("MYALPHA_TG_BOT_TOKEN", None)
assert dg.send_telegram("x") == "not_configured"
print("PASS give_up alert dedup")
