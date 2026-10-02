import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ee",ROOT/"scripts"/"event_evidence_engine.py")
ee=importlib.util.module_from_spec(spec);spec.loader.exec_module(ee)

planner={"today":[
 {"kind":"market_anomaly","key":"MSFT"},
 {"kind":"market_anomaly","key":"VGT"},
 {"kind":"failure_review","key":"LITE"},
],"queue":[]}
assert ee.selected_symbols(planner)==["MSFT","VGT","LITE"]

payload={"news":[
 {"title":"Microsoft announces new AI infrastructure agreement","publisher":"Reuters","providerPublishTime":1790870400,"link":"https://example/r","relatedTickers":["MSFT"]},
 {"title":"Why I think Microsoft could soar","publisher":"BlogSite","providerPublishTime":1790870000,"link":"https://example/o","relatedTickers":["MSFT"]},
]}
rows=ee.normalize_news(payload,5)
assert rows[0]["source_type"]=="newswire"
assert rows[0]["source_priority"]==1
assert rows[1]["source_type"]=="opinion"
assert rows[1]["source_priority"]==4

data={"stocks":{
 "GOOGL":{"day_chg":0.02},"AMZN":{"day_chg":0.03},"META":{"day_chg":0.01},"ORCL":{"day_chg":-0.01},
 "COHR":{"day_chg":0.04},"CIEN":{"day_chg":0.03},"AVGO":{"day_chg":0.02},"MRVL":{"day_chg":0.01},
}}
peer=ee.peer_context("LITE",data)
assert peer["peer_count"]==4
assert peer["direction"]=="broad_positive"

def fake_news(sym,limit=5):
    return rows[:1]
old=ee.fetch_news;ee.fetch_news=fake_news
try:
    out=ee.build(planner,data,{})
finally:
    ee.fetch_news=old
assert out["version"]=="6.4.1"
assert out["counts"]["selected"]==3
assert out["counts"]["ok"]==3
assert out["counts"]["news_items"]==3
assert out["policy"]["full_market_crawl"] is False
assert out["policy"]["automatic_orders"] is False
print("PASS V6.4 event and peer evidence layer")

payload_mixed={"news":[
 {"title":"Palantir growth story","publisher":"Media","relatedTickers":["PLTR"]},
 {"title":"Why ServiceNow (NOW) Stock Is Up Today","publisher":"StockStory","relatedTickers":["NOW"]},
 {"title":"Unrelated article without tickers","publisher":"Media","relatedTickers":[]},
]}
filtered=ee.normalize_news(payload_mixed,5,"NOW")
assert len(filtered)==1
assert "ServiceNow" in filtered[0]["title"]
assert ee.relevant_to_symbol({"title":"Microsoft launches product","relatedTickers":[]},"MSFT") is True
assert ee.relevant_to_symbol({"title":"Amazon launches product","relatedTickers":[]},"MSFT") is False
