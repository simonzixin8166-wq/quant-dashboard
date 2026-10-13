"""B2-02: clean subset only, look-ahead guarded, n shown, never used in decisions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fundamental_reliability as fr  # noqa: E402

def obs(oid, unit="USD", start="2026-01-01", end="2026-03-31", yoy=25.0):
    return {"observation_id": oid, "metrics": {"revenue": {"unit": unit, "start": start, "end": end, "value": 1, "yoy_pct": yoy}}}
O = [obs("q"), obs("rub", unit="RUB"), obs("ytd", start="2026-01-01", end="2026-09-30"), obs("neg", yoy=-5.0), obs("late")]
X = [{"observation_id": "q", "symbol": "AAA", "filed": "2026-04-20", "horizon_sessions": 20, "horizon_end": "2026-05-18", "return_pct": 4.0},
     {"observation_id": "q", "symbol": "AAA", "filed": "2026-04-20", "horizon_sessions": 60, "horizon_end": "2026-07-15", "return_pct": -2.0},
     {"observation_id": "rub", "symbol": "NBIS", "filed": "2026-04-20", "horizon_sessions": 20, "horizon_end": "2026-05-18", "return_pct": 9.0},
     {"observation_id": "ytd", "symbol": "AAA", "filed": "2026-10-20", "horizon_sessions": 20, "horizon_end": "2026-11-18", "return_pct": 9.0},
     {"observation_id": "neg", "symbol": "BBB", "filed": "2026-04-20", "horizon_sessions": 20, "horizon_end": "2026-05-18", "return_pct": -3.0},
     {"observation_id": "late", "symbol": "AAA", "filed": "2026-09-01", "horizon_sessions": 20, "horizon_end": "2026-10-20", "return_pct": 7.0}]
rows = fr.clean_rows(O, X)
assert {r[0] for r in rows} == {"AAA", "BBB"} and not any(r[0] == "NBIS" for r in rows)   # RUB excluded
assert not any(r[1] == "2026-10-20" for r in rows)                                       # YTD period excluded
c = fr.context("AAA", 0.25, "2026-10-09", "2026-10-10T00:00:00Z", rows, {"x": 1})
assert c["used_in_decision"] is False and c["yoy_bucket"] == "> +10%"
assert c["symbol"]["20"]["n"] == 1 and c["symbol"]["60"]["n"] == 1                        # 'late' window closes 10-20 > 10-09
assert c["pooled"]["20"]["n"] == 1 and c["status"] == "insufficient_n"                     # BBB is a different bucket
assert fr.context("AAA", None, "2026-10-09", "2026-10-10", rows, {}) is None
c2 = fr.context("AAA", 0.25, "2026-12-31", "2026-08-01", rows, {})                          # filed after lock excluded
assert c2["symbol"]["20"]["n"] == 1
assert fr.bucket(0.05) == 0 and fr.bucket(-0.01) == -1 and fr.bucket(0.2) == 1
s = fr.summary()
assert s["clean_outcomes_by_horizon"] and "market_state_outcome_scorecards" in s["disconnected"]
print("test_fundamental_reliability OK")
