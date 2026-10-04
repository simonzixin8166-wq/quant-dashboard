import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_statistical_controls import positive_control,repeated_negative_control,leakage_canary

spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
pos=positive_control(spec)
assert pos["pass"] is True
assert pos["effective_n"]>=20
assert pos["ci_lower"]>0
assert (pos["fdr"] or {}).get("reject") is True

neg=repeated_negative_control(spec,seeds=20,max_false_rate=0.30)
assert neg["pass"] is True
assert neg["false_promotion_rate"]<=0.30

leak=leakage_canary(spec)
assert leak["pass"] is True
assert leak["pre_ingest_event_rejected"] is True
assert leak["future_price_mutation_does_not_change_prior_baseline"] is True
print("PASS V6.15.8c positive / repeated-negative / leakage controls")
