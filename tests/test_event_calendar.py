"""UX-02 event calendar: official macro + FRED official release dates + unofficial earnings, display only,
fail-soft with cached fallback, and never written into market_events.json (options L2 window, OS-5-08).
Offline fixtures only; no network, no PyYAML, no wall-clock dates."""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import event_calendar as ec

NOW = dt.datetime(2026, 10, 26, 8, 0, tzinfo=dt.timezone.utc)
MARKET = {"source_status": {"CPI": "fresh", "FOMC": "fresh"}, "events": [
    {"type": "FOMC", "title": "FOMC利率决议日", "datetime": "2026-10-28T14:00:00-04:00", "source": "Federal Reserve",
     "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
    {"type": "CPI", "title": "CPI", "datetime": "2026-11-10T08:30:00-05:00", "source": "BLS", "source_url": "x"},
    {"type": "FOMC", "datetime": "2027-06-09T14:00:00-04:00", "source": "Federal Reserve"},          # outside window
    {"type": "CPI", "datetime": "2026-10-14T08:30:00-04:00", "source": "BLS"}]}                      # past
FRED = {50: ["2026-11-06", "2026-12-04"], 46: ["2026-11-13"], 53: ["2026-10-29", "2026-11-25"], 54: ["2026-10-30"],
        10: ["2026-11-10"]}
fred_calls = []
def fred(rid, key, start):
    fred_calls.append(rid)
    assert key == "K" and start == "2026-10-25"
    return {"release_dates": [{"release_id": rid, "date": d} for d in FRED[rid]]}
CAL = {"NVDA": {"Earnings Date": [dt.date(2026, 11, 18)]}, "AMD": {"Earnings Date": [dt.date(2026, 11, 3), dt.date(2026, 11, 5)]},
       "TSLA": {"Earnings Date": [dt.date(2027, 1, 27)]}, "SOFI": {}}
def cal(sym):
    if sym == "IREN":
        raise TimeoutError()
    return CAL.get(sym, {})
DATA = {"stocks": {"NVDA": {}, "AMD": {}, "TSLA": {}, "SOFI": {}, "IREN": {}}}

out = ec.build(MARKET, DATA, {}, "K", NOW, fred_get_fn=fred, earnings_fetch=cal, pause=0)
by = {e["key"]: e for e in out["events"]}
# official FOMC/CPI kept as official, out-of-window rows dropped
assert by["fomc_2026-10-28"]["time_status"] == "official" and "fomc_2027-06-09" not in by and "cpi_2026-10-14" not in by
# FRED: NFP/PPI/GDP/PCE dates at 08:30 ET labelled as standard time; CPI not re-fetched while BLS is fresh
assert by["nfp_2026-11-06"]["datetime"] == "2026-11-06T08:30:00-05:00" and by["nfp_2026-11-06"]["time_status"] == "official_date_standard_time"
assert by["gdp_2026-10-29"]["datetime"] == "2026-10-29T08:30:00-04:00" and "pce_2026-10-30" in by and "ppi_2026-11-13" in by
assert 10 not in fred_calls and "nfp_2026-12-04" in by
# earnings: unofficial, range kept as range, out of window skipped, missing listed - never guessed
assert by["earnings_NVDA_2026-11-18"]["time_status"] == "unofficial_date" and by["earnings_NVDA_2026-11-18"]["datetime"] is None
amd = by["earnings_AMD_2026-11-03"]
assert amd["time_status"] == "unofficial_estimated_range" and amd["date_end"] == "2026-11-05"
assert not any(k.startswith("earnings_TSLA") for k in by)
assert out["earnings_coverage"] == {"watchlist": 5, "with_date": 3, "unknown": ["IREN", "SOFI"]}
# contract: display only, sorted, statuses visible
assert out["policy"] == "display_only" and out["production_use"] is False and out["used_in_decision"] is False
assert [e["date"] for e in out["events"]] == sorted(e["date"] for e in out["events"])
assert out["source_status"]["NFP"] == "fresh" and out["source_status"]["EARNINGS"] == "fresh"

# BLS only cached -> FRED CPI fills the gap (but never duplicates an official CPI date)
fred_calls.clear()
cached = dict(MARKET, source_status={"CPI": "cached", "FOMC": "fresh"})
out2 = ec.build(cached, DATA, {}, "K", NOW, fred_get_fn=fred, earnings_fetch=cal, pause=0)
assert 10 in fred_calls and sum(1 for e in out2["events"] if e["type"] == "CPI") == 1

# outages: no FRED key / FRED errors / earnings fetch errors -> previous upcoming rows kept as cached, past dropped
prev = {"events": [dict(by["nfp_2026-11-06"]), dict(by["earnings_NVDA_2026-11-18"]),
                   {"key": "earnings_IREN_2026-11-12", "category": "earnings", "type": "EARNINGS", "symbol": "IREN",
                    "date": "2026-11-12", "title_zh": "IREN 财报"},
                   {"key": "nfp_2026-10-02", "category": "macro", "type": "NFP", "date": "2026-10-02"}]}
def boom(*a, **k):
    raise OSError("down")
out3 = ec.build(MARKET, DATA, prev, "K", NOW, fred_get_fn=boom, earnings_fetch=cal, pause=0)
k3 = {e["key"]: e for e in out3["events"]}
assert k3["nfp_2026-11-06"]["cached"] is True and "nfp_2026-10-02" not in k3
assert out3["source_status"]["NFP"] == "unavailable:OSError"
assert k3["earnings_IREN_2026-11-12"]["cached"] is True                    # symbol failed this run -> previous kept
assert "cached" not in k3["earnings_NVDA_2026-11-18"]                       # refreshed fresh
out4 = ec.build(MARKET, DATA, {}, "", NOW, fred_get_fn=fred, earnings_fetch=cal, pause=0)
assert out4["source_status"]["GDP"] == "unavailable:no_api_key" and not any(e["type"] == "GDP" for e in out4["events"])

# end to end on temp files; market_events.json is never written by this module
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    saved = (ec.MARKET_EVENTS, ec.DATA, ec.OUT)
    try:
        ec.MARKET_EVENTS, ec.DATA, ec.OUT = d / "m.json", d / "data.json", d / "cal.json"
        ec.MARKET_EVENTS.write_text(json.dumps(MARKET))
        ec.DATA.write_text(json.dumps({"stocks": {}}))
        assert ec.main() == 0 and json.loads(ec.OUT.read_text())["policy"] == "display_only"
        assert json.loads(ec.MARKET_EVENTS.read_text()) == MARKET
    finally:
        ec.MARKET_EVENTS, ec.DATA, ec.OUT = saved
src = (ROOT / "scripts" / "event_calendar.py").read_text(encoding="utf-8")
assert "MARKET_EVENTS.write" not in src and "market_events.json\").write" not in src
# the committed placeholder exists so the front-end never 404s before the first Daily run (E-14)
ph = json.loads((ROOT / "docs" / "data" / "event_calendar.json").read_text(encoding="utf-8"))
assert ph["policy"] == "display_only" and ph["used_in_decision"] is False and isinstance(ph["events"], list)
print("PASS UX-02 event calendar: official macro + FRED dates + unofficial earnings, display only, cached fallback")
