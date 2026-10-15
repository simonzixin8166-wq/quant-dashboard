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
assert v["2026-10-14"]["verdict"] == "on_time" and v["2026-10-14"]["delay_min"] == 20
assert v["2026-10-13"]["verdict"] == "degraded" and v["2026-10-13"]["guardian_recoveries"] == 1
assert v["2026-10-12"]["verdict"] == "gap" and v["2026-10-08"]["verdict"] == "gap"
assert s["on_time"] == 1 and s["degraded"] == 1 and s["gap"] == 3
j = {"update": {"expected_session": "2026-10-14"}, "coverage": [{"symbol": "AAPL", "last_date": "2026-10-14"},
     {"symbol": "IWM", "last_date": "2026-10-13"}, {"symbol": "VIX", "last_date": "2026-10-10"}]}
o = w.ohlcv_40(j)
assert o["complete"] == 1 and o["universe"] == 2 and o["stale"] == ["IWM"]
assert w.ohlcv_40({})["status"] == "unavailable" and w.forward_mature({})["status"] == "unavailable"
f = w.build(runs, today, j, {"snapshot": {"market": {"numeric": {"forward_mature_20": 0}}}}, {"counts": {"open": 0}})
assert w.changed(f, None) and not w.changed(f, {"fields": f}) and w.changed(f, {"fields": {**f, "open_incidents": 1}})
assert w.build(runs, today, j, {}, None)["open_incidents"] == "unavailable"
msg = w.message(f)
assert "1/5" in msg and "1/2" in msg and "UNPROVEN" in msg
u = w.build(None, today, j, {}, None)
assert u["schedule_7d"] == {"status": "unavailable"} and "Daily 准点（schedule）：unavailable" in w.message(u)
print("PASS weekly change summary")
