"""OFI-A1 (#133): closing option snapshot — universe/privacy/window/merge/fail-closed, no signals, private storage only."""
import json, os, sys
from datetime import date, datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import option_chain_snapshot as o  # noqa: E402

# universe: held first, canonical GOOGL→GOOG, de-dup, non-securities dropped, capped
u, dropped = o.build_universe(["QQQ", "IREN", "NVDA"], ["GOOGL", "iren", "ORCL", "BTC/USD"], cap=4)
assert u == ["GOOG", "IREN", "ORCL", "QQQ"] and dropped == ["NVDA"], (u, dropped)
assert o.build_universe(o.CONTEXT_UNIVERSE, [])[0] == o.CONTEXT_UNIVERSE

# window: +60d, ±20 %; unknown price → no strike filter (never guessed)
w = o.window(100.0, date(2026, 10, 13))
assert w == {"expiration_lte": "2026-12-12", "strike_gte": 80.0, "strike_lte": 120.0}
assert o.window(None, date(2026, 10, 13))["strike_gte"] is None

# run gate: 21:30Z on a session day yes; 08:15Z no; weekend no; force yes
assert o.should_run(datetime(2026, 10, 13, 21, 30, tzinfo=timezone.utc))[0]
assert not o.should_run(datetime(2026, 10, 13, 8, 15, tzinfo=timezone.utc))[0]
assert not o.should_run(datetime(2026, 10, 17, 21, 30, tzinfo=timezone.utc))[0]
assert o.should_run(datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc), force=True)[0]

OI = {"s": "ok", "pages": 1, "truncated": False, "optionSymbol": ["IREN261120C00050000", "IREN261120P00040000"],
      "expiration": ["2026-11-20", "2026-11-20"], "strike": [50, 40], "side": ["call", "put"], "multiplier": [100, 100],
      "openInterest": [1200, None], "openInterestDate": ["2026-10-12", None], "closePrice": [3.1, 1.2], "closePriceDate": ["2026-10-12", "2026-10-12"]}
CH = {"s": "ok", "pages": 1, "truncated": False, "optionSymbol": ["IREN261120C00050000", "IREN261120C00055000"],
      "expiration": ["2026-11-20", "2026-11-20"], "strike": [50, 55], "side": ["call", "call"], "bid": [3.0, 1.5], "ask": [3.2, 1.7],
      "last": [3.1, None], "iv": [0.9, 0.95], "delta": [0.55, 0.4], "gamma": [None, None], "theta": [None, None], "vega": [None, None],
      "volume": [340, None], "updated": [1, 2]}
rows = o.merge(OI, CH)
assert [r[0] for r in rows] == ["IREN261120C00050000", "IREN261120C00055000", "IREN261120P00040000"]
r0 = dict(zip(o.ROW_FIELDS, rows[0]))
assert r0["open_interest"] == 1200 and r0["open_interest_date"] == "2026-10-12" and r0["volume_day"] == 340 and r0["side"] == "C"
r1 = dict(zip(o.ROW_FIELDS, rows[1]))
assert r1["open_interest"] is None and r1["open_interest_date"] is None  # never back-filled
q = o.quality(rows, "2026-10-13")
assert q["contracts"] == 3 and q["oi_coverage"] == round(1 / 3, 4) and q["oi_is_prior_session_or_older"] is True


class FakeLedger:
    def __init__(self): self.calls = []
    def append_many(self, stream, records, market_date):
        self.calls.append((stream, records, market_date))
        class R: added_count = len(records); record_count = len(records); head_hash = "h" * 64
        return R()


def fake_http(url, headers):
    if "/rest/v1/options_positions" in url:
        return [{"symbol": "IREN", "status": "open"}, {"symbol": "OLD", "status": "closed"}]
    if "/rest/v1/stock_positions" in url:
        return [{"symbol": "ORCL"}]
    if "action=oi_window" in url:
        return OI
    if "action=chain_window" in url:
        if "symbol=SOFI" in url:
            raise TimeoutError("x")
        return CH
    raise AssertionError(url)


os.environ.update(SUPABASE_URL="https://example.invalid", SUPABASE_KEY="k")
os.environ.pop("MAV_OPTION_UNIVERSE", None)
led = FakeLedger()
st, recs = o.run(now=datetime(2026, 10, 13, 21, 40, tzinfo=timezone.utc), http=fake_http, ledger=led)
syms = [r["symbol"] for r in recs]
assert syms[:2] == ["IREN", "ORCL"] and "OLD" not in syms and set(o.CONTEXT_UNIVERSE) <= set(syms)
assert led.calls and led.calls[0][0] == o.STREAM and led.calls[0][2] == "2026-10-13"
assert all(r["record_id"] == f"ocs:2026-10-13:{r['symbol']}" for r in recs)
assert all(r["used_in_decision"] is False and r["signal"] is None and r["feed"] == "indicative" for r in recs)
sofi = next(r for r in recs if r["symbol"] == "SOFI")
assert sofi["status"] == "error" and sofi["rows"] == []
assert st["status_code"] == "partial" and st["underlyings_failed"] == 1 and st["used_in_decision"] is False

# public status: aggregate only — no symbol, no position, no OCC anywhere
blob = json.dumps(st)
for s in syms + ["IREN261120", "OLD"]:
    assert s not in blob, s
assert "symbols" not in st and "universe" not in st

# fail-closed: no ledger → nothing fetched, status unavailable
def boom(url, headers):
    raise AssertionError("must not fetch without a private ledger")
st2, recs2 = o.run(now=datetime(2026, 10, 13, 21, 40, tzinfo=timezone.utc), http=boom, ledger=None)
assert st2["status_code"] == "unavailable" and recs2 == []
# outside window → skipped, nothing fetched
st3, _ = o.run(now=datetime(2026, 10, 13, 8, 15, tzinfo=timezone.utc), http=boom, ledger=led)
assert st3["status_code"] == "skipped"
print("test_option_chain_snapshot OK")
