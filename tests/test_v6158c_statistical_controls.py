import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_statistical_controls import positive_control,repeated_negative_control,leakage_canary

spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
assert spec["spec_version"]=="1.3"
pos=positive_control(spec)
assert pos["pass"] is True
assert pos["effective_n"]>=20
assert pos["time_clusters"]>=6
assert pos["ci_lower"]>0
assert (pos["fdr"] or {}).get("reject") is True
assert pos["hypotheses_declared"]==3  # one synthetic family x 3 declared horizons

neg=repeated_negative_control(spec,seeds=500,max_false_rate_upper=0.10)
assert neg["seeds"]>=500
assert neg["pass"] is True
assert neg["wilson95"]["upper"]<=0.10

leak=leakage_canary(spec)
assert leak["pass"] is True
assert leak["pre_ingest_event_rejected"] is True
assert leak["future_price_mutation_does_not_change_prior_baseline"] is True
print("PASS V6.15.8e overlap-cluster positive / 500-seed negative / leakage controls")
