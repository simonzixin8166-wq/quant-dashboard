import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_rule_registry import build

def reading(ops):
    return {"version":"x","records":[{"source_id":"s1","symbols":["ABC"],"author":"a","published_at":"2026-01-01","url":"u","title":"t","propositions":[
      {"kind":"testable_rule","evidence":{"operation_index":i,"attribution":"author_plan","rule":op,"method_candidates":["M"]}}
      for i,op in enumerate(ops)
    ]}]}
source={"records":[{"id":"s1","operations":[{"x":1},{"x":2}]}],"operation_cases":[{"id":"s1","operations":[{"x":1},{"x":2}]}]}
r1=build(reading([
 {"fields":{"entry_1":10},"conditions":[],"actions":["buy"]},
 {"fields":{"entry_1":20},"conditions":[],"actions":["buy"]},
]),source,now="t1")
r2=build(reading([
 {"fields":{"entry_1":20},"conditions":[],"actions":["buy"]},
 {"fields":{"entry_1":10},"conditions":[],"actions":["buy"]},
]),source,now="t2")
assert {x["rule_id"] for x in r1["rules"]}=={x["rule_id"] for x in r2["rules"]}

# Exact duplicate semantic rules remain two registry rows.
dup=build(reading([
 {"fields":{"entry_1":10},"conditions":[],"actions":["buy"]},
 {"fields":{"entry_1":10},"conditions":[],"actions":["buy"]},
]),source,now="t1")
assert len(dup["rules"])==2
assert len({x["rule_id"] for x in dup["rules"]})==2

bad={"records":[{"id":"s1","operations":[{"x":1}]}],"operation_cases":[{"id":"s1","operations":[{"x":2}]}]}
try:
    build(reading([]),bad,now="t")
    raise AssertionError("mismatch should fail")
except ValueError:
    pass
print("PASS V6.15.1 immutable Rule Registry")


# Forward-only formation guard.
def source_store_for(sid,cls="genuine_forward"):
    return {"records":[{
      "source_key":sid,"admission_class":cls,
      "ingest_type":"live_ingest" if cls=="genuine_forward" else "backfill_ingest",
      "first_fetched_at":"2026-10-10T00:00:00+00:00",
      "first_fetched_at_origin":"source_store_first_observation",
      "timestamp_confidence":"high" if cls=="genuine_forward" else "unverified",
      "effective_forward_eligible":True if cls=="genuine_forward" else False,
      "effective_forward_reason":"eligible" if cls=="genuine_forward" else "not_genuine_live_admission",
      "record":{"id":sid}
    }]}

feature_prior={"rules":[],"source_observations":[{
  "source_id":"already-baselined","first_registry_seen_at":"2026-10-09T00:00:00Z",
  "first_extractor_version":"x","first_extractor_input_hash":"h",
  "latest_extractor_version":"x","latest_extractor_input_hash":"h"
}]}

# New genuine-forward source with its rule on first registry observation is eligible.
initial=build(
 reading([{"fields":{"entry_1":10},"conditions":[],"actions":["buy"]}]),
 source,
 feature_prior,
 now="2026-10-10T00:00:00Z",
 source_store=source_store_for("s1"),
)
ir=[x for x in initial["rules"] if x.get("source_id")=="s1" and x.get("active")][0]
assert ir["extraction_mode"]=="forward_initial"
assert ir["forward_eligible"] is True
assert ir["effective_forward_eligible"] is True

# A genuine source observed once with no rule cannot later create a new forward-eligible rule.
empty_reading={"version":"x","records":[{
 "source_id":"s1","symbols":["ABC"],"author":"a","published_at":"2026-01-01",
 "url":"u","title":"t","extractor_input_hash":"same","extractor_input_scope":"scope","propositions":[]
}]}
seen=build(empty_reading,{"records":[{"id":"s1","operations":[]}],"operation_cases":[]},feature_prior,
           now="2026-10-10T00:00:00Z",source_store=source_store_for("s1"))
assert any(x.get("source_id")=="s1" for x in seen["source_observations"])
later_reading={"version":"x","records":[{
 "source_id":"s1","symbols":["ABC"],"author":"a","published_at":"2026-01-01",
 "url":"u","title":"t","extractor_input_hash":"same","extractor_input_scope":"scope",
 "propositions":[{"kind":"testable_rule","evidence":{"operation_index":0,"attribution":"author_plan",
 "rule":{"fields":{"entry_1":10},"conditions":[],"actions":["buy"]},"method_candidates":[]}}]
}]}
later_source={"records":[{"id":"s1","operations":[{"x":1}]}],"operation_cases":[]}
later=build(later_reading,later_source,seen,now="2026-11-10T00:00:00Z",source_store=source_store_for("s1"))
lr=[x for x in later["rules"] if x.get("source_id")=="s1" and x.get("active")][0]
assert lr["extraction_mode"]=="retroactive"
assert lr["forward_eligible"] is False
assert lr["effective_forward_eligible"] is False

# Source-observation lifecycle survives reading-window eviction.
evicted=build({"version":"x","records":[]},{"records":[],"operation_cases":[]},later,
              now="2026-11-11T00:00:00Z",source_store=source_store_for("s1"))
assert any(x.get("source_id")=="s1" for x in evicted["source_observations"])
print("PASS forward-only rule formation / source-observation lifecycle")
