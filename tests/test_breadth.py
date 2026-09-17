import datetime
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
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
for key in ("b20", "b50", "b200"):
    assert 0 <= result[key] <= 1
assert -1 <= result["slope_10d"] <= 1

cached = dashboard._cached_breadth(result, "test fallback")
assert cached["status"] == "ok" and cached["is_cached"] is True
assert cached["date"] == result["date"]

print("test_breadth.py: all assertions passed")
