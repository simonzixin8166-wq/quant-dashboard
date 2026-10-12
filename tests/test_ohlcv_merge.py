"""D-05/D-06 regression: no synthetic OHLC, idempotent, conflicts quarantined, missing stays missing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ohlcv_merge as m  # noqa: E402

E = "2026-10-12"
hist = {"2026-10-09": (81.72, 81.81, 80.37, 81.28, 1e6)}
# TQQQ-style close-only row (docs/data.json core/index) → close_only, never written as a full bar
st, b = m.normalize_bar({"date": "2026-10-12", "close": 82.0}, E)
assert st == "close_only"
res, h2 = m.merge_bar(hist, st, b)
assert res["result"] == "close_only" and h2 == hist and "2026-10-12" not in h2
# full bar appends once; re-run is unchanged (idempotent)
row = {"date": "2026-10-12", "open": 81.5, "high": 82.4, "low": 81.1, "close": 82.0, "volume": 5e5}
st, b = m.normalize_bar(row, E); assert st == "ok"
res, h3 = m.merge_bar(hist, st, b); assert res["result"] == "appended" and h3["2026-10-12"][1] == 82.4
res, h4 = m.merge_bar(h3, *m.normalize_bar(row, E)); assert res["result"] == "unchanged" and h4 == h3
# different values for an existing date → conflict, history untouched
res, h5 = m.merge_bar(h3, *m.normalize_bar({**row, "close": 83.0, "high": 83.1}, E))
assert res["result"] == "conflict" and h5 == h3
# not-yet-final session, missing row, inconsistent OHLC, extreme gap
assert m.normalize_bar({**row, "date": "2026-10-13"}, E)[0] == "not_final"
assert m.normalize_bar(None, E)[0] == "missing" and m.normalize_bar({"date": E}, E)[0] == "missing"
assert m.normalize_bar({**row, "low": 90.0}, E)[0] == "invalid"
res, _ = m.merge_bar(hist, *m.normalize_bar({**row, "open": 200, "high": 201, "low": 199, "close": 200}, E))
assert res["result"] == "quarantined"
# input history is never mutated
assert hist == {"2026-10-09": (81.72, 81.81, 80.37, 81.28, 1e6)}
# the current production helper still back-fills close-only rows → this is the D-06 defect the migration removes
import local_history_agent as lha  # noqa: E402
legacy = lha.dashboard_bar({"core": {"TQQQ": {"date": "2026-10-12", "close": 82.0}}}, "TQQQ")
assert legacy and float(legacy["open"]) == float(legacy["high"]) == float(legacy["low"]) == 82.0, "documented legacy behaviour changed; update D-06 status"
print("test_ohlcv_merge OK")
