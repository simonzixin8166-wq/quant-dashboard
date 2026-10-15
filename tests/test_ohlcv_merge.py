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
# D-06 wired: the production helper no longer back-fills close-only rows
import json, tempfile  # noqa: E402
import pandas as pd  # noqa: E402
import local_history_agent as lha  # noqa: E402
legacy = lha.dashboard_bar({"core": {"TQQQ": {"date": "2026-10-12", "close": 82.0}}}, "TQQQ")
assert legacy["open"] is None and legacy["high"] is None and legacy["low"] is None and legacy["close"] == 82.0
assert m.normalize_bar(legacy, E)[0] == "close_only"

# D-05 / D-06 end-to-end on a temp archive: display-independent universe, close-only never written,
# fallback accepted only with a verified price basis, missing stays missing, re-run idempotent.
def _df(rows):
    d = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    d["date"] = pd.to_datetime(d["date"]); return d.set_index("date")
base = [("2026-10-08", 10, 11, 9, 10.5, 1), ("2026-10-09", 10.5, 11, 10, 10.8, 1)]
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    lha.ARCHIVE, lha.DASHBOARD, lha.REGISTRY = t / "a.zip", t / "data.json", t / "reg.json"
    lha.REGISTRY.write_text(json.dumps({"universes": {"data_collection_universe": ["AAPL", "TQQQ", "SPY", "MU", "XLE", "NEWX"]}}))
    lha.DASHBOARD.write_text(json.dumps({
        "stocks": {"SPY": {"date": "2026-10-12", "open": 10.9, "high": 11.2, "low": 10.7, "close": 11.0, "volume": 5}},
        "core": {"TQQQ": {"date": "2026-10-12", "close": 12.0}}}))
    store = {s: _df(base) for s in ("AAPL", "TQQQ", "SPY", "MU", "XLE")}
    lha.write_archive(store)
    calls = []
    def fake(symbols):
        calls.append(sorted(symbols))
        ok = [{"date": "2026-10-09", "open": 10.5, "high": 11, "low": 10, "close": 10.81, "volume": 1},
              {"date": "2026-10-12", "open": 10.8, "high": 11.3, "low": 10.6, "close": 11.1, "volume": 2},
              {"date": "2026-10-13", "open": 11, "high": 11.5, "low": 10.9, "close": 11.2, "volume": 2}]  # not final
        return {"AAPL": ok, "TQQQ": [], "MU": [{**r, "close": r["close"] * 1.2, "high": r["high"] * 1.2} for r in ok],
                "XLE": [ok[1]]}
    st = lha.read_archive()
    r = lha.append_latest(st, fetch_fallback=fake, expected="2026-10-12")
    app = {(a["symbol"], a["date"]): a["source"] for a in r["appended"]}
    assert app[("SPY", "2026-10-12")].startswith("docs/data.json stocks")              # displayed: full OHLC from site data
    assert app[("AAPL", "2026-10-12")].startswith("Yahoo")                             # not displayed: still updated
    assert ("AAPL", "2026-10-13") not in app                                            # unfinished session never written
    assert any(c["symbol"] == "TQQQ" for c in r["close_only"]) and "TQQQ" in r["missing"]  # close-only → stale, not a flat bar
    q = {x["symbol"]: x["reason"] for x in r["quarantined"]}
    assert q["MU"] == "fallback_basis_mismatch" and q["XLE"] == "fallback_basis_unverified"
    assert "NEWX" in r["missing"] and calls == [["AAPL", "MU", "TQQQ", "XLE"]]
    st2 = lha.read_archive()
    assert st2["AAPL"].index.max() == pd.Timestamp("2026-10-12") and st2["TQQQ"].index.max() == pd.Timestamp("2026-10-09")
    assert st2["MU"].index.max() == pd.Timestamp("2026-10-09") and "NEWX" not in st2
    r2 = lha.append_latest(st2, fetch_fallback=fake, expected="2026-10-12")         # idempotent re-run
    assert not r2["appended"] and "SPY" in r2["unchanged"]
    # a different value for an already archived date is quarantined, never overwritten
    lha.DASHBOARD.write_text(json.dumps({"stocks": {"SPY": {"date": "2026-10-12", "open": 10.9, "high": 11.2, "low": 10.7, "close": 11.05, "volume": 5}}}))
    r3 = lha.append_latest(lha.read_archive(), fetch_fallback=lambda s: {}, expected="2026-10-12")
    assert any(x["symbol"] == "SPY" and x["reason"] == "conflict" for x in r3["quarantined"])
    assert float(lha.read_archive()["SPY"].loc["2026-10-12", "close"]) == 11.0

# P0-2 (2026-10-15): second free fallback only for symbols the first one left without the expected session;
# same basis guard; every request logged (requested, returned last date, HTTP status / error).
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    lha.ARCHIVE, lha.DASHBOARD, lha.REGISTRY = t / "a.zip", t / "data.json", t / "reg.json"
    lha.REGISTRY.write_text(json.dumps({"universes": {"data_collection_universe": ["IWM", "HYG", "TLT"]}}))
    lha.DASHBOARD.write_text(json.dumps({}))
    lha.write_archive({s: _df(base) for s in ("IWM", "HYG", "TLT")})
    ok = [{"date": "2026-10-09", "open": 10.5, "high": 11, "low": 10, "close": 10.8, "volume": 1},
          {"date": "2026-10-12", "open": 10.8, "high": 11.3, "low": 10.6, "close": 11.1, "volume": 2}]
    first_calls, second_calls = [], []
    def first(symbols):
        first_calls.append(sorted(symbols))
        return {"IWM": ok, "HYG": ok[:1], "TLT": []}          # HYG/TLT: source has not published 10-12 yet
    def second(symbols):
        second_calls.append(sorted(symbols))
        return {"HYG": ok, "TLT": [{**r, "close": r["close"] * 1.3, "high": r["high"] * 1.3} for r in ok]}
    r = lha.append_latest(lha.read_archive(), fetch_fallback=first, fetch_fallback2=second, expected="2026-10-12")
    src = {a["symbol"]: a["source"] for a in r["appended"]}
    assert src == {"IWM": "Yahoo (yfinance) fallback", "HYG": "Yahoo chart v8 fallback"}, src
    assert second_calls == [["HYG", "TLT"]]                                        # only the still-lacking symbols
    assert {x["symbol"]: x["reason"] for x in r["quarantined"]} == {"TLT": "fallback_basis_mismatch"}
    assert "fallback_attempts" in r
    bc = r["basis_check"]
    assert bc["HYG"]["overlap_sessions"] == 1 and bc["HYG"]["max_abs_close_diff_pct"] == 0.0
    assert bc["TLT"]["max_abs_close_diff_pct"] > 0.5 and bc["HYG"]["returned_last_date"] == "2026-10-12"
    # no second fallback configured → behaviour identical to before (HYG stays missing, fail-closed)
    lha.write_archive({s: _df(base) for s in ("IWM", "HYG", "TLT")})
    r0 = lha.append_latest(lha.read_archive(), fetch_fallback=first, expected="2026-10-12")
    assert "HYG" in r0["missing"] and "TLT" in r0["missing"]

# chart parser: rows with any missing O/H/L/C are skipped (never synthesized); HTTP errors are recorded
import io as _io, urllib.error  # noqa: E402
class _Resp(_io.BytesIO):
    status = 200
def opener(url):
    if "TLT" in url:
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
    body = {"chart": {"result": [{"timestamp": [1760362200, 1760448600],   # 2025-10-13/14 13:30Z → NY dates
                                  "indicators": {"quote": [{"open": [1.0, None], "high": [1.2, 1.3], "low": [0.9, 1.0],
                                                            "close": [1.1, 1.2], "volume": [100, 200]}]}}]}}
    return _Resp(json.dumps(body).encode())
lha.FALLBACK_DIAG.clear()
out = lha._yahoo_chart_recent(["HYG", "TLT"], opener=opener, pause=0)
assert [r["date"] for r in out["HYG"]] == ["2025-10-13"] and out["HYG"][0]["open"] == 1.0
assert "TLT" not in out
d = lha.FALLBACK_DIAG[-1]["per_symbol"]
assert d["TLT"]["http_status"] == 429 and d["TLT"]["error"] == "HTTPError" and d["HYG"]["http_status"] == 200
assert d["HYG"]["returned_last_date"] == "2025-10-13" and d["TLT"]["returned_last_date"] is None
print("test_ohlcv_merge OK")
