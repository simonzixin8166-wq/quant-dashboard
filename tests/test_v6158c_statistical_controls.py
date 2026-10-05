import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_statistical_controls import (
    positive_control,repeated_negative_control,realism_negative_controls,
    leakage_canary,power_curve
)

spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
assert spec["spec_version"]=="1.7"

pos=positive_control(spec)
assert pos["pass"] is True
assert pos["effective_n"]>=20
assert pos["time_clusters"]>=6
assert pos["ci_lower"]>0
assert (pos["fdr"] or {}).get("reject") is True
assert pos["hypotheses_declared"]==3

neg=repeated_negative_control(spec,seeds=500,max_false_rate_upper=0.10)
assert neg["seeds"]>=500
assert neg["pass"] is True
assert neg["wilson95"]["upper"]<=0.10

real=realism_negative_controls(spec,seeds=500,max_false_rate_upper=0.10)
assert real["pass"] is True
assert {x["name"] for x in real["scenarios"]}=={
    "minimum_6_clusters_iid","serial_ar1_rho_0_35","heavy_tail_student_t3"
}
for row in real["scenarios"]:
    assert row["seeds"]>=500
    assert row["wilson95"]["upper"]<=0.10
min6=[x for x in real["scenarios"] if x["name"]=="minimum_6_clusters_iid"][0]
assert min6["clusters"]==6
assert min6["effective_units"]>=20

leak=leakage_canary(spec)
assert leak["pass"] is True
assert leak["pre_ingest_event_rejected"] is True
assert leak["future_price_mutation_does_not_change_prior_baseline"] is True
assert leak["shifted_entry_future_mutation_invariant"] is True
assert leak["label_and_event_order_permutation_invariant"] is True

power=power_curve(spec,seeds=20)
assert power["diagnostic_only"] is True
assert power["threshold_tuning_allowed"] is False
assert len(power["points"])==12
assert {x["effect"] for x in power["points"]}=={0.0,0.005,0.01,0.02}
assert {x["clusters"] for x in power["points"]}=={6,8,12}
print("PASS V6.15.8f realistic nulls / power curve / expanded leakage canaries")
