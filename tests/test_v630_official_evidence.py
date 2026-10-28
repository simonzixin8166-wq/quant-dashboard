import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("oe",ROOT/"scripts"/"official_evidence_engine.py")
oe=importlib.util.module_from_spec(spec);spec.loader.exec_module(oe)

planner={"today":[
 {"kind":"market_anomaly","key":"MSFT"},
 {"kind":"market_anomaly","key":"VGT"},
 {"kind":"failure_review","key":"LITE"},
],"queue":[]}
assert oe.selected_symbols(planner)==["IREN","SOFI","MSFT","LITE"]

ticker_payload={"0":{"cik_str":789019,"ticker":"MSFT","title":"MICROSOFT CORP"},
                "1":{"cik_str":1633978,"ticker":"LITE","title":"LUMENTUM HOLDINGS INC"},
                "2":{"cik_str":1878848,"ticker":"IREN","title":"IREN LIMITED"},
                "3":{"cik_str":1818874,"ticker":"SOFI","title":"SOFI TECHNOLOGIES INC"}}
submissions={
 "name":"MICROSOFT CORP",
 "filings":{"recent":{
   "form":["10-Q","8-K","4"],
   "accessionNumber":["0001-26-000001","0001-26-000002","0001-26-000003"],
   "primaryDocument":["msft10q.htm","msft8k.htm","xslF345.htm"],
   "filingDate":["2026-09-30","2026-09-20","2026-09-18"],
   "reportDate":["2026-09-30","2026-09-20","2026-09-18"],
 }}
}

def fake_json(url,ua):
    if "company_tickers" in url:return ticker_payload
    return submissions

def fake_text(url,ua):
    return "<html><body>Item 2.02 Results of Operations Revenue increased. Item 8.01 Other Events test.</body></html>"

oldj,oldt=oe.request_json,oe.request_text
oe.request_json,oe.request_text=fake_json,fake_text
try:
    out=oe.build(planner,{},"MyAlpha Test")
finally:
    oe.request_json,oe.request_text=oldj,oldt

assert out["version"]=="6.3.0"
assert out["counts"]["selected"]==4
assert out["counts"]["mapped"]==4
assert out["counts"]["filings"]==8
assert out["counts"]["with_excerpts"]==8
msft=out["symbols"]["MSFT"]
assert msft["status"]=="ok"
assert msft["filings"][0]["form"]=="10-Q"
assert msft["filings"][0]["excerpts"]
assert "Results of Operations" in msft["filings"][0]["excerpts"][0]
assert out["policy"]["automatic_orders"] is False
print("PASS V6.3 SEC official evidence layer")


# #133 6117163110 P0-A: unverified author self-report reviews (no learning_eligible=true) never select symbols
review_evidence={"failure_attribution":{"external_outcome_reviews":[{"symbol":"NOW"},{"symbol":"NBIS"},{"symbol":"CRWV"},{"symbol":"MU"}]}}
gated=oe.selected_symbols(planner,review_evidence)
assert gated[:2]==["IREN","SOFI"]
for sym in ["NOW","NBIS","CRWV","MU"]:
    assert sym not in gated or sym in [str(x.get("key")) for x in (planner.get("today") or [])+(planner.get("queue") or [])]
# independently verified reviews (learning_eligible=true) still expand the collection set
verified={"failure_attribution":{"external_outcome_reviews":[{"symbol":s,"learning_eligible":True} for s in ("NOW","NBIS","CRWV","MU")]}}
expanded=oe.selected_symbols(planner,verified)
assert expanded[:2]==["IREN","SOFI"]
for sym in ["MSFT","LITE","NOW","NBIS","CRWV","MU"]:
    assert sym in expanded
assert len(expanded)<=14
print("PASS V6.15 official evidence learning-review expansion")

crowded_planner={"today":[{"kind":"market_anomaly","key":"MSFT"},{"kind":"market_anomaly","key":"LITE"}],
                 "queue":[{"kind":"market_anomaly","key":x} for x in ["AMD","NVDA","TSLA","ORCL","META","AMZN","AVGO","QCOM","JPM","PYPL"]]}
crowded=oe.selected_symbols(crowded_planner,verified)  # verified reviews keep priority over the backlog
for sym in ["NOW","NBIS","CRWV","MU"]:
    assert sym in crowded, crowded
assert not any(s in oe.selected_symbols(crowded_planner,review_evidence) for s in ["NOW","NBIS","CRWV","MU"]), "unverified reviews never jump the queue"
assert len(crowded)<=14
print("PASS learning-review priority over backlog queue")

# 2026-10-25: SEC's ticker directory returned 403 (official_evidence.json @aeb2048c). The engine is fail-soft and
# records ticker_directory_error; the Public Leak Guard must accept that root key, otherwise a transient SEC outage
# during Daily would fail Daily's verify step (the same class as E-01).
import json as _json, sys as _sys
_sys.path.insert(0, str(ROOT / "scripts"))
import private_guardrail as _pg
def _boom(url, ua):
    raise RuntimeError("HTTP Error 403: Forbidden")
oldj = oe.request_json
oe.request_json = _boom
try:
    down = oe.build(planner, {}, "MyAlpha Test", archive=[])
finally:
    oe.request_json = oldj
assert down["ticker_directory_status"] == "error" and down["ticker_directory_error"] == "HTTP Error 403: Forbidden"
_path = ROOT / "docs" / "research" / "official_evidence.json"
assert _pg.schema_findings(_path, _json.dumps(down)) == [], _pg.schema_findings(_path, _json.dumps(down))
assert set(down) <= _pg.PUBLIC_JSON_ROOT_ALLOWLIST["docs/research/official_evidence.json"]
print("PASS official evidence SEC outage stays fail-soft and guardrail-clean")

# E-17 (10/27): a directory outage must not erase known filings. Before the fix every symbol became "unmapped" with
# empty filings, and auto_thesis / fundamental_outcome_context recomputed to 0 (direct-company 11 -> 0, mature_20 24 -> 0).
sel = oe.selected_symbols(planner)
s0, s1 = sel[0], sel[1]
FIX = {"form": "10-Q", "accession": "0000000000-26-000001", "filing_date": "2026-10-01", "report_date": "2026-09-30",
       "primary_document": "q.htm", "url": "https://www.sec.gov/x/q.htm", "document_status": "ok", "excerpts": ["FIXTURE"]}
prev = {"symbols": {s0: {"status": "ok", "cik": 111, "company_name": "Prev Co", "filings": [FIX]},
                    s1: {"status": "unmapped", "filings": []}}}                       # already degraded, no cik
arch = [dict(FIX, symbol=s1, cik=222, company_name="Arch Co", accession=f"0000000000-26-00000{i}",
             filing_date=f"2026-0{i}-15") for i in range(1, 6)]
oe.request_json = _boom
try:
    kept = oe.build(planner, prev, "MyAlpha Test", archive=arch)
finally:
    oe.request_json = oldj
a, b = kept["symbols"][s0], kept["symbols"][s1]
assert a["status"] == "stale_cache" and a["filings"] == [FIX] and a["cik"] == 111                      # previous file
assert b["status"] == "stale_cache" and b["cik"] == 222 and b["cache_source"] == "archive"             # archive
assert [f["filing_date"] for f in b["filings"]] == ["2026-05-15", "2026-04-15", "2026-03-15"]           # newest 3
assert all("symbol" not in f and "archive_id" not in f for f in b["filings"])                           # filing shape only
others = [v for k, v in kept["symbols"].items() if k not in (s0, s1)]
assert others and all(v["status"] == "unmapped" and v["filings"] == [] for v in others)                # nothing invented
assert kept["counts"]["stale_cache"] == 2 and kept["counts"]["filings"] == 4 and kept["counts"]["ok"] == 0
assert _pg.schema_findings(_path, _json.dumps(kept)) == []
# directory down but submissions reachable: the cached CIK is used and the symbol refreshes normally
def _dir_only(url, ua):
    if url == oe.SEC_TICKERS:
        raise RuntimeError("HTTP Error 403: Forbidden")
    return fake_json(url, ua)
oe.request_json, oe.request_text = _dir_only, fake_text
try:
    part = oe.build(planner, prev, "MyAlpha Test", archive=arch)
finally:
    oe.request_json, oe.request_text = oldj, oldt
assert part["ticker_directory_status"] == "error" and part["symbols"][s0]["status"] == "ok" and part["symbols"][s0]["cik"] == 111
print("PASS E-17 SEC directory outage keeps last known filings as stale_cache (previous file, then archive)")
