import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_persistent_source_store import migrate_sources,append_event_history

visible=[
 {"id":"s1","source":"wenxuecity","source_kind":"blog","published_at":"2020-01-01","title":"t1","url":"u1","operations":[]},
 {"id":"s2","source":"feed","source_kind":"post","published_at":"2020-01-02","title":"t2","url":"u2","operations":[]},
]
source={"counts":{"records":2},"records":visible}
a=migrate_sources(source,now="2026-10-04T00:00:00Z",full_records=visible)
assert len(a["records"])==2
assert all(x["first_fetched_at"]=="2026-10-04T00:00:00Z" for x in a["records"])
assert all(x["first_fetched_at"]!=x.get("published_at") for x in a["records"])
assert a["records"][0]["timestamp_confidence"] in {"high","unverified","missing"}
assert a["records"][0]["content_hash_scope"]=="normalized_title_excerpt_only"
assert a["records"][0]["raw_fulltext_hash_status"]=="unavailable_unless_preserved_by_upstream_source"
assert a["records"][0]["normalized_available_text_hash"]

# Recover one row that was outside the original visible window.
full=visible+[{"id":"s3","source":"feed","source_kind":"post","published_at":"2019-01-01","title":"old","url":"u3","operations":[]}]
source2={"counts":{"records":3},"records":visible}
b=migrate_sources(source2,a,now="2026-10-05T00:00:00Z",full_records=full)
assert len(b["records"])>=source2["counts"]["records"]
by={x["source_key"]:x for x in b["records"]}
assert by["s1"]["first_fetched_at"]=="2026-10-04T00:00:00Z"
assert by["s3"]["first_fetched_at"]=="2026-10-05T00:00:00Z"
assert by["s3"]["ingest_type"]=="backfill_ingest"
assert by["s3"]["first_fetched_at"]!=by["s3"]["published_at"]

# Fail closed if pre-window ingestion is incomplete.
try:
    migrate_sources({"counts":{"records":3},"records":visible},a,now="t",full_records=visible)
    raise AssertionError("incomplete pre-window ingest should fail")
except RuntimeError:
    pass

events={"events":[{"event_id":"e1","rule_id":"r1","spec_version":"1.0","scores":{}}]}
h1=append_event_history(events,now="t1")
h2=append_event_history(events,h1,now="t2")
assert len(h1["records"])==1 and len(h2["records"])==1
events2={"events":[{"event_id":"e1","rule_id":"r1","spec_version":"1.1","scores":{}}]}
h3=append_event_history(events2,h2,now="t3")
assert len(h3["records"])==2
print("PASS V6.15.8a full pre-window persistence / backfill provenance / event history")
