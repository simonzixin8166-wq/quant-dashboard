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
for key in ("b20", "b50", "b200"):
    assert 0 <= result[key] <= 1
assert -1 <= result["slope_10d"] <= 1

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

print("test_breadth.py: all assertions passed")
