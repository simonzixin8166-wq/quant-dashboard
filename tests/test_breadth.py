import datetime
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
try:
    import yfinance  # noqa: F401
except ModuleNotFoundError:
    sys.modules["yfinance"] = types.SimpleNamespace(download=lambda *args, **kwargs: None)
spec = importlib.util.spec_from_file_location("dashboard", ROOT / "scripts" / "fetch_and_build.py")
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)

end = pd.Timestamp(datetime.date.today() - datetime.timedelta(days=1))
dates = pd.bdate_range(end=end, periods=330)
rng = np.random.default_rng(7)
returns = rng.normal(0.0004, 0.012, size=(330, 503))
prices = 100 * np.exp(np.cumsum(returns, axis=0))
closes = pd.DataFrame(prices, index=dates, columns=[f"S{i:03d}" for i in range(503)])

result = dashboard._compute_breadth_from_closes(closes)
assert result["status"] == "ok"
assert result["symbols"] == 503
assert result["coverage"] == 503
assert result["coverage_pct"] == 1
assert result["quality_gate"] == "pass"
for key in ("b20", "b50", "b200", "advance_pct", "decline_pct", "unchanged_pct", "new_high_52w_pct", "near_high_52w_pct", "new_low_52w_pct"):
    assert 0 <= result[key] <= 1
assert -1 <= result["slope_10d"] <= 1
assert -1 <= result["ad_net_pct"] <= 1
assert -20 <= result["ad_line_20d"] <= 20
assert -60 <= result["ad_line_60d"] <= 60

cached = dashboard._cached_breadth(result, "test fallback")
assert cached["status"] == "ok" and cached["is_cached"] is True
assert cached["date"] == result["date"]

fixed_now = datetime.datetime(2026, 9, 24, 14, 0)
fresh = dashboard.breadth_freshness({"status":"ok", "date":"2026-09-23"}, fixed_now)
assert fresh["tone"] == "good" and "2026-09-23" in fresh["label"]
stale = dashboard.breadth_freshness({"status":"ok", "date":"2026-09-18", "is_cached":True}, fixed_now)
assert stale["tone"] == "bad" and "数据陈旧" in stale["label"]

try:
    dashboard._compute_breadth_from_closes(closes.iloc[:, :449])
    raise AssertionError("449 symbols must fail the 450/90% breadth quality gate")
except ValueError as exc:
    assert "覆盖不足" in str(exc)


# Regression guard: a source snapshot older than the cached breadth must never win.
assert dashboard._breadth_date({"date":"2026-09-25"}) == datetime.date(2026, 9, 25)
assert dashboard._breadth_date({"date":"bad"}) is None

# Morning skip is only valid when cache already covers the latest completed session.
# At 2026-09-29 02:00 UTC the latest completed US weekday is 2026-09-28.
expected = dashboard._previous_completed_us_session(datetime.datetime(2026, 9, 29, 2, 0))
assert expected == datetime.date(2026, 9, 28)
assert datetime.date(2026, 9, 24) < expected

print("test_breadth.py: all assertions passed")
