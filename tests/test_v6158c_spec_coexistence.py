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
 {"event_id":"e1","spec_version":"1.4","score_hash":"newhash","score":{"data_quality":{"price_series_hash":"px"}}}
]}
out=build(history,"1.4")
assert out["counts"]["records_by_spec"]=={"1.0":1,"1.1":1,"1.2":1,"1.3":1,"1.4":1}
assert out["counts"]["events_with_current"]==1
assert out["counts"]["events_with_prior_and_current"]==1
assert out["counts"]["preserved_prior_records"]==4
row=out["events"][0]
assert row["current_score_hash"]=="newhash"
assert {x["score_hash"] for x in row["prior_versions"]}=={"oldhash","midhash","v12hash","v13hash"}
assert all(x["record_preserved"] for x in row["prior_versions"])
print("PASS V6.15.8g append-only EventScore Spec 1.4 coexistence audit")
