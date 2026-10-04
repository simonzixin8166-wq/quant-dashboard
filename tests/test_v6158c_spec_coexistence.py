import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_spec_coexistence_audit import build

history={"records":[
 {"event_id":"e1","spec_version":"1.0","score_hash":"oldhash","score":{"data_quality":{"price_series_hash":"px"}}},
 {"event_id":"e1","spec_version":"1.1","score_hash":"newhash","score":{"data_quality":{"price_series_hash":"px"}}}
]}
out=build(history)
assert out["counts"]["legacy_v1_0_records"]==1
assert out["counts"]["current_v1_1_records"]==1
assert out["counts"]["events_with_both"]==1
row=out["events"][0]
assert row["legacy_score_hash"]=="oldhash"
assert row["legacy_record_preserved"] is True
assert row["price_series_hash_equal"] is True
print("PASS V6.15.8c old/new EventScore coexistence audit")
