import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_rule_family import build,structural_key,verify_definition

spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
definition=json.loads((ROOT/"research/specs/rule_family_definition.json").read_text())
assert verify_definition(definition)==definition["definition_hash"]
assert definition["normalizer_version"]=="v615_rule_registry.normalize_rule@6.15.1"
assert definition["extractor_version"]=="source_reading_memory@6.14.6"
assert spec["spec_version"]=="1.3"
assert spec["thresholds"]["independent_authors_min"]==3
assert spec["thresholds"]["independent_time_clusters_min"]==6
assert spec["thresholds"]["mature_60_effective_samples_min"]==20
assert spec["thresholds"]["lift_ci95_lower_bound_gt"]==0.0

base={
 "rule_id":"r1","active":True,"author":"author-a","source_id":"s1",
 "symbols":["ABC"],"method_candidates":["趋势确认"],
 "normalized_rule":{"fields":{"entry_1":100.0,"exit_line":90.0},"conditions":["breakout above resistance"],"actions":["buy"]},
}
variant=copy.deepcopy(base)
variant["rule_id"]="r2";variant["author"]="another-author";variant["source_id"]="s2"
variant["normalized_rule"]["fields"]["entry_1"]=200.0
variant["normalized_rule"]["fields"]["exit_line"]=150.0
assert structural_key(base,definition)==structural_key(variant,definition)

rules={"rules":[base,variant]}
out=build(rules,spec,definition,{},now="t1")
assert out["counts"]["active_assignments"]==2
assert out["counts"]["active_families"]==1
assert len({x["family_id"] for x in out["assignments"]})==1

# Same definition hash cannot silently reassign an existing rule.
prior=copy.deepcopy(out)
tampered=copy.deepcopy(prior)
tampered["assignments"][0]["family_id"]="family_tampered"
try:
    build(rules,spec,definition,tampered,now="t2")
    raise AssertionError("immutable family assignment should fail")
except ValueError:
    pass
print("PASS V6.15.8b result-blind immutable Rule Family definition")
