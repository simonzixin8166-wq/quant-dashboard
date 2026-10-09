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
