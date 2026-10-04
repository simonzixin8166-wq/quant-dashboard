import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

from autonomous_research_planner import build as planner_build
from self_improvement_engine import build as self_build
from controlled_learning_policy import method_states
from learning_evaluation_engine import method_rows

legacy_method={
 "evidence_role":"legacy_descriptive_only",
 "methods":[{
   "method":"趋势确认",
   "direct_validated_events":999,
   "context_validated_events":999,
   "performance":{"20":{"alignment_rate":0.99,"n":999}},
   "evidence_maturity":{"state":"outcome_supportive","mature_n":999},
   "source_reading":{"testable_rule_candidates":2}
 }]
}
legacy_evidence={
 "external_outcome_evidence_role":"legacy_descriptive_only",
 "failure_attribution":{"external_outcome_reviews":[
   {"symbol":"ABC","event_id":f"e{i}","tags":["bad"]} for i in range(50)
 ]}
}

# Planner may keep structural rule-candidate work, but must not create legacy
# failure-review / outcome-maturity tasks.
planner=planner_build({}, {}, legacy_evidence, legacy_method, {}, {}, {}, {}, {}, {}, {}, {})
kinds={x.get("kind") for x in planner.get("queue") or []}
assert "failure_review" not in kinds
assert "method_evidence_gap" not in kinds
assert "method_validation" not in kinds
assert "method_rule_candidate" in kinds

# Self Improvement cannot create method research weights or legacy-outcome guards.
self_out=self_build(legacy_evidence,legacy_method,{}, {}, {}, {}, {}, {}, {}, {})
legacy_candidates=[
 x for x in self_out.get("candidates") or []
 if x.get("scope") in {"趋势确认","failure_review"}
]
assert legacy_candidates==[]

# Controlled Learning and Learning Evaluation expose the legacy status but
# suppress old performance as validated maturity.
state=method_states(legacy_method)["趋势确认"]
assert state["state"]=="legacy_descriptive_only"
assert state["direct_n"]==0
assert state["alignment20"] is None
rows=method_rows(legacy_method)
assert rows[0]["maturity"]=="legacy_descriptive_only"
assert rows[0]["direct_validated_events"]==0
assert rows[0]["horizons"]=={}

# Ablation: deleting old outcome payloads cannot change the actionable legacy outputs.
ablated_method=copy.deepcopy(legacy_method)
m=ablated_method["methods"][0]
m["direct_validated_events"]=0;m["context_validated_events"]=0;m["performance"]={};m["evidence_maturity"]={}
ablated_evidence={"external_outcome_evidence_role":"legacy_descriptive_only","failure_attribution":{"external_outcome_reviews":[]}}
planner2=planner_build({}, {}, ablated_evidence, ablated_method, {}, {}, {}, {}, {}, {}, {}, {})
assert [(x.get("kind"),x.get("key"),x.get("priority")) for x in planner.get("tasks") or []] == [(x.get("kind"),x.get("key"),x.get("priority")) for x in planner2.get("queue") or []]
assert method_states(legacy_method)==method_states(ablated_method)
assert method_rows(legacy_method)==method_rows(ablated_method)
print("PASS V6.15.8d-2 legacy Outcome bypass ablation")
