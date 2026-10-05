import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_persistent_source_store import migrate_sources,append_event_history,select_current_event_records,canonical_url,secondary_identity_fingerprint,normalize_text

visible=[
 {"id":"s1","source":"wenxuecity","source_kind":"blog","published_at":"2020-01-01","title":"t1","url":"u1","operations":[]},
 {"id":"s2","source":"feed","source_kind":"post","published_at":"2020-01-02","title":"t2","url":"u2","operations":[]},
]
source={"counts":{"records":2},"records":visible}
a=migrate_sources(source,now="2026-10-04T00:00:00Z",full_records=visible)
assert len(a["records"])==2
assert all(x["first_fetched_at"]=="2026-10-04T00:00:00Z" for x in a["records"])
assert all(x["first_fetched_at_origin"]=="source_store_first_observation" for x in a["records"])
assert all(x["admission_class"]=="initial_migration" for x in a["records"])
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
assert by["s1"]["ingest_type"]=="initial_migration"
assert by["s1"]["first_fetched_at_origin"]=="source_store_first_observation"
assert by["s3"]["first_fetched_at"]=="2026-10-05T00:00:00Z"
assert by["s3"]["ingest_type"]=="backfill_ingest"
assert by["s3"]["first_fetched_at"]!=by["s3"]["published_at"]
assert b["source_accounting"]["current_upstream_records"]==3
assert b["source_accounting"]["persistent_records_total"]==3
assert b["source_accounting"]["retained_historical_records"]==0
assert b["source_accounting"]["current_ingest_complete"] is True

# Append-only history is retained but must be separated from current ingestion.
current=[visible[0],full[2]]
c=migrate_sources({"counts":{"records":2},"records":current},b,now="2026-10-06T00:00:00Z",full_records=current)
assert len(c["records"])==3
assert c["source_accounting"]["current_upstream_records"]==2
assert c["source_accounting"]["persistent_records_total"]==3
assert c["source_accounting"]["retained_historical_records"]==1
assert c["source_accounting"]["current_ingest_complete"] is True
cby={x["source_key"]:x for x in c["records"]}
assert cby["s2"]["source_still_online"] is False

# Fail closed if pre-window ingestion is incomplete.
try:
    migrate_sources({"counts":{"records":3},"records":visible},a,now="t",full_records=visible)
    raise AssertionError("incomplete pre-window ingest should fail")
except RuntimeError:
    pass

events={"events":[{"event_id":"e1","rule_id":"r1","spec_version":"1.0","scoring_engine_version":"event_score@test1","scores":{}}]}
h1=append_event_history(events,now="t1")
h2=append_event_history(events,h1,now="t2")
assert len(h1["records"])==1 and len(h2["records"])==1
events2={"events":[{"event_id":"e1","rule_id":"r1","spec_version":"1.1","scoring_engine_version":"event_score@test2","scores":{}}]}
h3=append_event_history(events2,h2,now="t3")
assert len(h3["records"])==2
print("PASS V6.15.8a full pre-window persistence / backfill provenance / event history")


# Duplicate revisions under the same event/spec remain audit history but project to one effective event.
dup={"version":"x","records":[
 {"event_id":"e1","spec_version":"1.5","scoring_engine_version":"event_score@a","score_hash":"a","recorded_at":"t1","score":{"event_id":"e1","spec_version":"1.5"}},
 {"event_id":"e1","spec_version":"1.5","scoring_engine_version":"event_score@b","score_hash":"b","recorded_at":"t2","score":{"event_id":"e1","spec_version":"1.5"}},
 {"event_id":"e2","spec_version":"1.5","scoring_engine_version":"event_score@b","score_hash":"c","recorded_at":"t2","score":{"event_id":"e2","spec_version":"1.5"}},
]}
current=select_current_event_records(dup,"1.5")
assert len(current)==2
assert {x["event_id"] for x in current}=={"e1","e2"}
assert [x for x in current if x["event_id"]=="e1"][0]["score_hash"]=="b"
print("PASS V6.15.8i one effective history revision per event/spec")


# Re-ingesting an existing source must never refresh first_fetched_at or promote its ingest type.
again=migrate_sources(source,a,now="2026-10-10T12:34:56Z",full_records=visible)
again_by={x["source_key"]:x for x in again["records"]}
assert again_by["s1"]["first_fetched_at"]=="2026-10-04T00:00:00Z"
assert again_by["s1"]["ingest_type"]=="initial_migration"
assert again_by["s1"]["first_fetched_at_origin"]=="source_store_first_observation"
print("PASS V6.15.8k immutable first_fetched_at / ingest_type re-ingest defense")


# Spec 1.7 canonical URL strips tracking and normalizes host/scheme.
assert canonical_url("http://www.Example.com/a/?utm_source=x&b=2&a=1#frag")=="https://example.com/a?a=1&b=2"

# Rekey defense: same historical article under a new upstream id/url variant inherits old provenance.
prior_article={"id":"old-id","source":"wenxuecity","source_kind":"blog","author":"A","published_at":"2026-10-01T00:00:00+00:00","title":"Same Story","url":"https://example.com/post?id=7&utm_source=old","operations":[]}
seed=migrate_sources({"counts":{"records":1},"records":[prior_article]},now="2026-10-04T00:00:00+00:00",full_records=[prior_article])
new_article=dict(prior_article);new_article["id"]="new-id";new_article["url"]="http://www.example.com/post?utm_medium=x&id=7"
rekey=migrate_sources({"counts":{"records":1},"records":[new_article]},seed,now="2026-10-05T12:00:00+00:00",full_records=[new_article])
rk=[x for x in rekey["records"] if x["source_key"]=="new-id"][0]
assert rk["admission_class"]=="rekeyed_duplicate"
assert rk["first_fetched_at"]=="2026-10-04T00:00:00+00:00"
assert rk["identity_parent_source_key"]=="old-id"
assert rk["ingest_type"]=="initial_migration"

# Same-batch secondary fingerprint collision is order independent and fails closed.
x1={"id":"x1","source":"feed","source_kind":"post","author":"Same","published_at":"2026-10-05","title":"Collision","url":"https://x.test/1","operations":[]}
x2={"id":"x2","source":"feed","source_kind":"post","author":"Same","published_at":"2026-10-05","title":"Collision","url":"https://x.test/2","operations":[]}
base_prior=seed
ab=migrate_sources({"counts":{"records":2},"records":[x1,x2]},base_prior,now="2026-10-05T12:00:00+00:00",full_records=[x1,x2])
ba=migrate_sources({"counts":{"records":2},"records":[x2,x1]},base_prior,now="2026-10-05T12:00:00+00:00",full_records=[x2,x1])
assert {r["source_key"]:r["admission_class"] for r in ab["records"] if r["source_key"] in {"x1","x2"}}=={"x1":"identity_ambiguous","x2":"identity_ambiguous"}
assert {r["source_key"]:r["admission_class"] for r in ba["records"] if r["source_key"] in {"x1","x2"}}=={"x1":"identity_ambiguous","x2":"identity_ambiguous"}

# High-confidence publication timestamp is veto-only. Exactly 3 calendar days remains eligible; >3 is late discovery.
fri={"id":"fri","source":"wenxuecity","source_kind":"blog","author":"A","published_at":"2026-10-02","title":"Friday","url":"https://example.com/fri","operations":[]}
mon=migrate_sources({"counts":{"records":1},"records":[fri]},seed,now="2026-10-05T12:00:00+00:00",full_records=[fri])
fr=[x for x in mon["records"] if x["source_key"]=="fri"][0]
assert fr["late_discovery_age_calendar_days"]==3
assert fr["admission_class"]=="genuine_forward"
old_pub=dict(fri);old_pub["id"]="oldpub";old_pub["published_at"]="2026-10-01";old_pub["title"]="Old";old_pub["url"]="https://example.com/oldpub"
late=migrate_sources({"counts":{"records":1},"records":[old_pub]},seed,now="2026-10-05T12:00:00+00:00",full_records=[old_pub])
lr=[x for x in late["records"] if x["source_key"]=="oldpub"][0]
assert lr["late_discovery_age_calendar_days"]==4
assert lr["admission_class"]=="late_discovery"
assert lr["ingest_type"]=="backfill_ingest"

# Admission classification is immutable across later runs.
again_late=migrate_sources({"counts":{"records":1},"records":[old_pub]},late,now="2026-10-06T12:00:00+00:00",full_records=[old_pub])
al=[x for x in again_late["records"] if x["source_key"]=="oldpub"][0]
assert al["admission_class"]=="late_discovery"
assert al["admission_classified_at"]==lr["admission_classified_at"]
print("PASS Spec 1.7 canonical identity / rekey / ambiguity / late-discovery admission")


# Hotfix: whitespace normalization must collapse all whitespace, including newlines.
assert normalize_text("  Hello   World \n x ")=="hello world x"

# A historical article re-keyed with only whitespace changes in title must inherit prior provenance.
ws_old={"id":"ws-old","source":"feed","source_kind":"post","author":"Alpha","published_at":"2026-10-05","title":"Hello   World\nX","url":"https://old.example/ws","operations":[]}
ws_seed=migrate_sources({"counts":{"records":1},"records":[ws_old]},now="2026-10-05T01:00:00+00:00",full_records=[ws_old])
# Simulate persisted pre-hotfix fingerprint corruption: the row stores an incompatible fingerprint.
ws_seed["records"][0]["secondary_identity_fingerprint"]="pre-hotfix-buggy-fingerprint"
ws_new=dict(ws_old);ws_new["id"]="ws-new";ws_new["url"]="https://new.example/ws";ws_new["title"]="Hello World X"
ws_rekey=migrate_sources({"counts":{"records":1},"records":[ws_new]},ws_seed,now="2026-10-05T02:00:00+00:00",full_records=[ws_new])
ws_row=[x for x in ws_rekey["records"] if x["source_key"]=="ws-new"][0]
assert ws_row["admission_class"]=="rekeyed_duplicate"
assert ws_row["identity_parent_source_key"]=="ws-old"
assert ws_row["first_fetched_at"]=="2026-10-05T01:00:00+00:00"
assert ws_row["ingest_type"]=="initial_migration"

# Rekey from a backfill parent stays non-forward and inherits the parent's first observation.
backfill_parent={"id":"bf-old","source":"feed","source_kind":"post","author":"Beta","published_at":"2026-09-01","title":"Backfill Parent","url":"https://old.example/bf","operations":[]}
bf_prior=migrate_sources(
 {"counts":{"records":1},"records":[]},
 ws_seed,
 now="2026-10-05T03:00:00+00:00",
 full_records=[backfill_parent]
)
bf_old=[x for x in bf_prior["records"] if x["source_key"]=="bf-old"][0]
assert bf_old["admission_class"]=="backfill"
assert bf_old["ingest_type"]=="backfill_ingest"
backfill_new=dict(backfill_parent);backfill_new["id"]="bf-new";backfill_new["url"]="https://new.example/bf"
bf_rekey=migrate_sources(
 {"counts":{"records":1},"records":[backfill_new]},
 bf_prior,
 now="2026-10-05T04:00:00+00:00",
 full_records=[backfill_new]
)
bf_new=[x for x in bf_rekey["records"] if x["source_key"]=="bf-new"][0]
assert bf_new["admission_class"]=="rekeyed_duplicate"
assert bf_new["ingest_type"]=="backfill_ingest"
assert bf_new["first_fetched_at"]==bf_old["first_fetched_at"]
print("PASS V6.15.8m whitespace normalization / persisted fingerprint recompute / backfill-parent rekey")
