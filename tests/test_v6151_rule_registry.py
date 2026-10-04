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
