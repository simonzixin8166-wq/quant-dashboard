import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_spec_coexistence_audit import build

history={"records":[
 {"event_id":"e1","spec_version":"1.0","score_hash":"oldhash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.1","score_hash":"midhash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.2","score_hash":"v12hash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.3","score_hash":"v13hash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.4","score_hash":"v14hash","recorded_at":"t4","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.5","scoring_engine_version":"event_score@a","score_hash":"newhash-a","recorded_at":"t5","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.5","scoring_engine_version":"event_score@b","score_hash":"newhash-b","recorded_at":"t6","score":{"data_quality":{"price_series_hash":"px"}}}
]}
out=build(history,"1.5")
assert out["counts"]["records_by_spec"]=={"1.0":1,"1.1":1,"1.2":1,"1.3":1,"1.4":1,"1.5":2}
assert out["counts"]["events_with_current"]==1
assert out["counts"]["events_with_prior_and_current"]==1
assert out["counts"]["preserved_prior_records"]==5
assert out["counts"]["event_spec_pairs_with_multiple_revisions"]==1
assert out["counts"]["current_effective_events"]==1
row=out["events"][0]
assert row["current_score_hash"]=="newhash-b"
assert row["current_scoring_engine_version"]=="event_score@b"
assert {x["score_hash"] for x in row["prior_versions"]}=={"oldhash","midhash","v12hash","v13hash","v14hash"}
assert all(x["record_preserved"] for x in row["prior_versions"])
print("PASS V6.15.8i append-only EventScore Spec 1.5 coexistence / current-effective revision audit")
