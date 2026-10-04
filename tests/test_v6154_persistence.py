import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_persistent_source_store import migrate_sources,append_event_history

source={"counts":{"records":1215},"records":[{"id":"s1","published_at":"2020-01-01","title":"t","url":"u","operations":[]}]}
a=migrate_sources(source,now="2026-10-04T00:00:00Z")
assert a["records"][0]["first_fetched_at"]=="2026-10-04T00:00:00Z"
assert a["records"][0]["first_fetched_at"]!=source["records"][0]["published_at"]
b=migrate_sources(source,a,now="2026-10-05T00:00:00Z")
assert b["records"][0]["first_fetched_at"]=="2026-10-04T00:00:00Z"

events={"events":[{"event_id":"e1","rule_id":"r1","spec_version":"1.0","scores":{}}]}
h1=append_event_history(events,now="t1")
h2=append_event_history(events,h1,now="t2")
assert len(h1["records"])==1 and len(h2["records"])==1
# New spec is retained alongside old result.
events2={"events":[{"event_id":"e1","rule_id":"r1","spec_version":"1.1","scores":{}}]}
h3=append_event_history(events2,h2,now="t3")
assert len(h3["records"])==2
print("PASS V6.15.4 persistent source/evaluation history")
