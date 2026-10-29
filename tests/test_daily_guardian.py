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

# main() fixture: give_up path in dry run never sends; an API failure on the alert lookup never breaks the guardian
import io, contextlib, json as _json, os as _o
calls = {"tg": 0}
dg.send_telegram = lambda text: calls.__setitem__("tg", calls["tg"] + 1) or "sent"
_now = datetime.now(timezone.utc)
_exp = dg.tc.expected_latest_completed_session(_now).isoformat()
_late = (dg.session_close_utc(dg.tc.expected_latest_completed_session(_now)) + dg.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
_g = [{"event": "workflow_dispatch", "status": "completed", "display_title": f"Daily Dashboard Update · daily-guardian {_exp} #{i}",
       "created_at": _late, "updated_at": _late} for i in (1, 2)]
def fake_gh(fail_guardian):
    def _gh(method, path, body=None):
        assert method == "GET", "fixture must never dispatch"
        if path.startswith("actions/workflows/daily.yml"):
            return {"workflow_runs": _g}
        if path.startswith("actions/workflows/daily-guardian.yml"):
            if fail_guardian:
                raise OSError("api down")
            return {"workflow_runs": []}
        return {"workflow_runs": []}
    return _gh
for fail in (False, True):
    dg.gh = fake_gh(fail)
    _o.environ["GUARD_DRY_RUN"] = "1"
    if _now >= dg.session_close_utc(dg.tc.expected_latest_completed_session(_now)) + dg.timedelta(minutes=dg.GRACE_MIN):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _o.environ["GUARD_INJECT_MARKET_AS_OF"] = "2000-01-03"
            assert dg.main() == 0
        out = buf.getvalue()
        assert "DAILY_STILL_STALE" in out and "SERVER_GUARD" in out
        assert ("GIVE_UP_ALERT skipped" in out) if fail else ("GIVE_UP_ALERT dry_run" in out)
assert calls["tg"] == 0
_o.environ.pop("GUARD_INJECT_MARKET_AS_OF", None); _o.environ.pop("GUARD_DRY_RUN", None)
print("PASS give_up main() dry-run fixture (no send, API failure tolerated)")

# Option B (Owner 10/29): a guard-dispatched Daily fires no workflow_run, so the guardian follows its own dispatch
# and refreshes Server Action Watch only after that Daily completed successfully.
class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def sleep(self, s): self.t += s
R = "daily-guardian 2026-10-28 #1"
mk = lambda status, conclusion=None, title=f"Daily Dashboard Update · {R}", created="2026-10-28T23:35:54Z": {
    "id": 1, "status": status, "conclusion": conclusion, "display_title": title, "created_at": created}
seq = [[], [mk("queued")], [mk("in_progress")], [mk("completed", "success")]]
c = FakeClock()
r = dg.follow_dispatched(R, lambda: seq.pop(0) if len(seq) > 1 else seq[0], sleep=c.sleep, clock=c, max_min=25, poll_sec=60)
assert r["result"] == "success" and c.t == 180
c = FakeClock()
assert dg.follow_dispatched(R, lambda: [mk("completed", "failure")], sleep=c.sleep, clock=c)["result"] == "failed"
c = FakeClock()
t = dg.follow_dispatched(R, lambda: [mk("in_progress")], sleep=c.sleep, clock=c, max_min=25, poll_sec=60)
assert t["result"] == "timeout" and c.t == 25 * 60
# another run's success (different run-name, e.g. the delayed scheduled Daily or attempt #2) is never taken for ours
c = FakeClock()
other = [mk("completed", "success", title="Daily Dashboard Update"), mk("completed", "success", title="Daily Dashboard Update · daily-guardian 2026-10-28 #2")]
assert dg.follow_dispatched(R, lambda: other, sleep=c.sleep, clock=c, max_min=3, poll_sec=60)["result"] == "timeout"
# transient API errors are tolerated within the budget
c = FakeClock(); n = {"i": 0}
def flaky():
    n["i"] += 1
    if n["i"] == 1: raise OSError("api")
    return [mk("completed", "success")]
assert dg.follow_dispatched(R, flaky, sleep=c.sleep, clock=c)["result"] == "success"

# main(): dispatch -> follow -> Server Action Watch refresh (success) / no refresh (failed); never in dry run
posts = []
def gh_follow(conclusion):
    def _gh(method, path, body=None):
        if method == "POST":
            posts.append((path, (body or {}).get("inputs", {}).get("run_reason"))); return None
        if path.startswith("actions/workflows/daily.yml/runs"):
            return {"workflow_runs": [mk("completed", conclusion)]}
        return {"workflow_runs": []}
    return _gh
orig_decide, orig_follow = dg.decide, dg.follow_dispatched
dg.decide = lambda now, m, runs: {"action": "dispatch", "reason": "stale_and_idle", "attempt": 1, "expected": "2026-10-28", "market_as_of": "2026-10-27"}
dg.follow_dispatched = lambda reason, lr: orig_follow(reason, lr, sleep=lambda s: None, clock=lambda: 0.0)
try:
    for concl, want in (("success", True), ("failure", False)):
        posts.clear(); dg.gh = gh_follow(concl); _o.environ["GUARD_DRY_RUN"] = "0"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert dg.main() == 0
        out = buf.getvalue()
        assert posts[0] == ("actions/workflows/daily.yml/dispatches", R), posts
        refreshed = ("actions/workflows/server-action-watch.yml/dispatches", "server-guardian after-daily 2026-10-28") in posts
        assert refreshed is want, (concl, posts)
        assert ("SERVER_REFRESH_AFTER_DAILY" in out) is want and "FOLLOW_DAILY" in out
        assert sum(1 for p_, _ in posts if "server-action-watch" in p_) == (1 if want else sum(1 for p_, _ in posts if "server-action-watch" in p_))
        if want:
            assert "SERVER_GUARD skipped" in out
    posts.clear(); dg.gh = gh_follow("success"); _o.environ["GUARD_DRY_RUN"] = "1"
    with contextlib.redirect_stdout(io.StringIO()):
        dg.main()
    assert posts == [], "dry run never dispatches or follows"
finally:
    dg.decide, dg.follow_dispatched = orig_decide, orig_follow
    _o.environ.pop("GUARD_DRY_RUN", None)
wf = (ROOT / ".github" / "workflows" / "daily-guardian.yml").read_text(encoding="utf-8")
assert "timeout-minutes: 32" in wf and "actions: write" in wf and "contents: read" in wf   # no permission change
print("PASS guardian follows its own Daily dispatch and refreshes Server Action Watch only after success")
