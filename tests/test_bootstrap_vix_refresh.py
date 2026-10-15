"""P0-2 (#133 6183848571): the VIX refresh never writes an unfinished session and never restates silently.
Regression for 2026-10-14: an intraday VIX bar (close 15.75 at 13:51Z) entered the archive as final, and the
10-13 close changed 15.40 → 15.27 without any log."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bootstrap_replay_history as b  # noqa: E402

def frame(rows):
    return pd.DataFrame([{"date": pd.Timestamp(d), "open": o, "high": h, "low": l, "close": c, "volume": 0} for d, o, h, l, c in rows])

existing = frame([("2026-10-09", 15, 16, 14, 15.5), ("2026-10-12", 15.39, 15.53, 15.11, 15.21), ("2026-10-13", 15.61, 15.61, 15.17, 15.40)])
recent = frame([("2026-10-09", 15, 16, 14, 15.9),          # older session differs → not applied, logged
                ("2026-10-12", 15.39, 15.53, 15.11, 15.21),  # unchanged
                ("2026-10-13", 15.61, 15.61, 15.17, 15.27),  # recent restatement → applied, logged
                ("2026-10-14", 15.17, 15.89, 14.98, 15.75)]) # intraday when expected session is 10-13 → dropped
m, rev, dropped = b.merge_refresh(existing, recent, "2026-10-13")
assert dropped == ["2026-10-14"] and m["date"].max() == pd.Timestamp("2026-10-13")
by = {r["date"]: r for r in rev}
assert by["2026-10-13"]["applied"] and by["2026-10-13"]["old"][3] == 15.40 and by["2026-10-13"]["new"][3] == 15.27
assert by["2026-10-09"]["applied"] is False and "2026-10-12" not in by
mm = m.set_index("date")
assert float(mm.loc["2026-10-13", "close"]) == 15.27 and float(mm.loc["2026-10-09", "close"]) == 15.5
# once 10-14 is the latest completed session, it is appended
m2, rev2, d2 = b.merge_refresh(m, recent, "2026-10-14")
assert not d2 and m2["date"].max() == pd.Timestamp("2026-10-14") and float(m2.set_index("date").loc["2026-10-14", "close"]) == 15.75
# idempotent: a re-run with the same data restates nothing more
m3, rev3, _ = b.merge_refresh(m2, recent, "2026-10-14")
assert [r for r in rev3 if r["applied"]] == [] and m3.equals(m2)
print("test_bootstrap_vix_refresh OK")
