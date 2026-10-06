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
