"""H-02 (#133 6138793593): macro-event artifact — DST-aware windows, stale → data_insufficient, inert."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import macro_event_watch as mew  # noqa: E402

out = mew.build(datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))
assert out["production_use"] is False and out["used_in_decision"] is False and out["automatic_orders"] is False
ev = {e["key"]: e for e in out["events"]}
assert ev["cpi_2026_09"]["windows"]["release"] == "2026-10-14T12:30:00Z"
assert ev["cpi_2026_09"]["windows"]["t_minus_1_start"] == "2026-10-13T04:00:00Z"        # EDT midnight
assert ev["treasury_refunding_2026_11_04"]["windows"]["event_day_start"] == "2026-11-04T05:00:00Z"  # EST after 11/01
# an outcome exists only once recorded after its official release (the committed calendar fills over time)
assert all(e["official_outcome"] is None or e["official_outcome"]["recorded_at"] >= e["release"]["utc"] for e in out["events"])
assert out["judgment"]["key"] in ("risk_elevated", "neutral_awaiting_confirmation", "conditions_improving", "data_insufficient")
txt = json.dumps(out, ensure_ascii=False)
for bad in ("马上买", "马上卖", "立即买入", "立即卖出"):
    assert bad not in txt
assert len(out["lines"]) == 3 and {l["tranche"] for l in out["lines"]} == {1, 2, 3}
# a later expected session than the data → data_insufficient (never the previous judgment)
# "later" is relative to the committed data (a fixed date stops being later once Daily advances the data — failed 10/20)
from datetime import date, timedelta
data_asof = date.fromisoformat(mew.build(datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))["freshness"]["market_as_of"])
late_day = data_asof + timedelta(days=7)
late = mew.build(datetime(late_day.year, late_day.month, late_day.day, 12, 0, tzinfo=timezone.utc))
assert late["freshness"]["data_stale"] and late["judgment"]["key"] == "data_insufficient"
print("PASS macro event watch")
