"""Weekly change summary: fixed fields, schedule-only on-time count, recovery never on-time, silent when unchanged."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekly_change_summary as w  # noqa: E402

today = date(2026, 10, 15)                                   # Thu → sessions 10-08,09,12,13,14 (10-10/11 weekend)
runs = [
    {"id": 1, "event": "schedule", "created_at": "2026-10-14T21:50:00Z", "conclusion": "success"},   # 10-13? no: 10-14 cron +20m
    {"id": 2, "event": "schedule", "created_at": "2026-10-14T00:28:55Z", "conclusion": "success"},   # 10-13 +2h58m
    {"id": 3, "event": "schedule", "created_at": "2026-10-13T02:40:09Z", "conclusion": "failure"},   # 10-12 failed
    {"id": 4, "event": "workflow_dispatch", "created_at": "2026-10-13T23:57:16Z", "conclusion": "success",
     "display_title": "Daily Dashboard Update · daily-guardian 2026-10-13 #1"},
    {"id": 5, "event": "schedule", "created_at": "2026-10-13T15:54:23Z", "conclusion": "success"},   # 08:15 cron: outside 12 h window of 10-12? (21:30→09:30) yes outside
]
s = w.schedule_week(runs, today)
v = {r["session"]: r for r in s["rows"]}
assert s["sessions"] == 5 and "2026-10-10" not in v
# Owner rule 2026-10-17: on time = schedule success finished before the next NYSE 09:30 ET open.
assert v["2026-10-14"]["verdict"] == "on_time" and v["2026-10-14"]["delay_min"] == 20
assert v["2026-10-13"]["verdict"] == "on_time" and v["2026-10-13"]["delay_min"] == 179   # +2h58m55s, before 10-14 open
assert v["2026-10-13"]["guardian_recoveries"] == 1
assert v["2026-10-12"]["verdict"] == "gap" and v["2026-10-08"]["verdict"] == "gap"
assert v["2026-10-14"]["next_open_utc"] == "2026-10-15T13:30:00Z"
assert s["on_time"] == 2 and s["degraded"] == 0 and s["gap"] == 3
# Friday session: next open is Monday; a run finishing after that open is degraded; a run created after the
# next weekday 08:15Z cron is not attributed to the 21:30Z slot; a guardian recovery never counts.
fri = w.schedule_week([
    {"id": 7, "event": "schedule", "created_at": "2026-10-17T06:00:00Z", "updated_at": "2026-10-17T06:15:00Z", "conclusion": "success"},
], date(2026, 10, 19))
assert {r["session"]: r["verdict"] for r in fri["rows"]}["2026-10-16"] == "on_time"
late = w.schedule_week([
    {"id": 8, "event": "schedule", "created_at": "2026-10-15T07:59:00Z", "updated_at": "2026-10-15T13:45:00Z", "conclusion": "success"},
    {"id": 9, "event": "schedule", "created_at": "2026-10-16T08:30:00Z", "conclusion": "success"},        # next-day 08:15 slot
    {"id": 10, "event": "workflow_dispatch", "created_at": "2026-10-16T01:00:00Z", "conclusion": "success",
     "display_title": "Daily Dashboard Update · daily-guardian 2026-10-15 #1"},
], date(2026, 10, 17))
lv = {r["session"]: r for r in late["rows"]}
assert lv["2026-10-14"]["verdict"] == "degraded"          # finished 13:45Z, after the 10-15 13:30Z open
assert lv["2026-10-15"]["verdict"] == "gap" and lv["2026-10-15"]["guardian_recoveries"] == 1
j = {"update": {"expected_session": "2026-10-14"}, "coverage": [{"symbol": "AAPL", "last_date": "2026-10-14"},
     {"symbol": "IWM", "last_date": "2026-10-13"}, {"symbol": "VIX", "last_date": "2026-10-10"}]}
o = w.ohlcv_40(j)
assert o["complete"] == 1 and o["universe"] == 2 and o["stale"] == ["IWM"]
assert w.ohlcv_40({})["status"] == "unavailable" and w.forward_mature({})["status"] == "unavailable"
f = w.build(runs, today, j, {"snapshot": {"market": {"numeric": {"forward_mature_20": 0}}}}, {"counts": {"open": 0}})
assert w.changed(f, None) and not w.changed(f, {"fields": f}) and w.changed(f, {"fields": {**f, "open_incidents": 1}})
assert w.build(runs, today, j, {}, None)["open_incidents"] == "unavailable"
msg = w.message(f)
assert "2/5" in msg and "1/2" in msg and "UNPROVEN" in msg
u = w.build(None, today, j, {}, None)
assert u["schedule_7d"] == {"status": "unavailable"} and "Daily 准点（schedule）：unavailable" in w.message(u)
print("PASS weekly change summary")
