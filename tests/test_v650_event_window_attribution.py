import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ew",ROOT/"scripts"/"event_window_attribution.py")
ew=importlib.util.module_from_spec(spec);spec.loader.exec_module(ew)

evidence={"failure_attribution":{"external_outcome_reviews":[
 {"event_id":"e1","symbol":"NBIS","published_at":"2026-09-08","title":"sample","review_tags":["large_adverse_move"],"return_20":-0.1}
]}}
official={"symbols":{"NBIS":{"filings":[
 {"form":"6-K","filing_date":"2026-09-08","url":"u1"},
 {"form":"6-K","filing_date":"2026-08-26","url":"u2"}
]}}}
events={"symbols":{"NBIS":{"news":[
 {"title":"event","publisher":"Newswire","source_type":"media","source_priority":3,"published_at":"2026-09-10T12:00:00+00:00","url":"n1"}
]}}}
out=ew.build(evidence,official,events)
assert out["version"]=="6.5.0"
assert out["summary"]["reviews"]==1
row=out["rows"][0]
assert row["nearest_sec"]["days_from_research"]==0
assert row["nearest_sec"]["distance_band"]=="very_near"
assert row["nearest_event"]["days_from_research"]==2
assert row["nearest_event"]["distance_band"]=="near"
assert row["guardrail"].startswith("日期接近")
assert out["policy"]["causal_claims"] is False
print("PASS V6.5 event-window attribution")
