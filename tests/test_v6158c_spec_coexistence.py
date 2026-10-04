import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_spec_coexistence_audit import build

history={"records":[
 {"event_id":"e1","spec_version":"1.0","score_hash":"oldhash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.1","score_hash":"midhash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.2","score_hash":"newhash","score":{"data_quality":{"price_series_hash":"px"}}}
]}
out=build(history,"1.2")
assert out["counts"]["records_by_spec"]=={"1.0":1,"1.1":1,"1.2":1}
assert out["counts"]["events_with_current"]==1
assert out["counts"]["events_with_prior_and_current"]==1
assert out["counts"]["preserved_prior_records"]==2
row=out["events"][0]
assert row["current_score_hash"]=="newhash"
assert {x["score_hash"] for x in row["prior_versions"]}=={"oldhash","midhash"}
assert all(x["record_preserved"] for x in row["prior_versions"])
print("PASS V6.15.8d generic append-only EventScore spec coexistence audit")
