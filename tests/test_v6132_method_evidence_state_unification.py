import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import learning_evaluation_engine as le
import controlled_learning_policy as cl

method={
 "counts":{"source_records":100,"eligible_triggered_events":7,"direct_method_links":6,"mature60_eligible_events":0},
 "methods":[
  {
   "method":"仓位与加减仓",
   "direct_validated_events":6,
   "status":"direct_developing",
   "evidence_maturity":{"state":"direct_developing","basis_horizon":20,"mature_n":5,"alignment_rate":None},
   "performance":{"20":{"n":5,"alignment_rate":0.6667,"avg_return":0.02,"median_return":0.01}},
  },
  {
   "method":"Sell Put",
   "direct_validated_events":0,
   "status":"context_only",
   "evidence_maturity":{"state":"context_only","basis_horizon":None,"mature_n":0,"alignment_rate":None},
   "performance":None,
  },
  {
   "method":"趋势确认",
   "direct_validated_events":10,
   "status":"outcome_supportive",
   "evidence_maturity":{"state":"outcome_supportive","basis_horizon":20,"mature_n":10,"alignment_rate":0.7},
   "performance":{"20":{"n":10,"alignment_rate":0.7,"avg_return":0.03,"median_return":0.02}},
  },
 ]
}

rows=le.method_rows(method)
by={x["method"]:x for x in rows}
assert by["仓位与加减仓"]["maturity"]=="direct_developing"
assert by["Sell Put"]["maturity"]=="context_only"
assert by["趋势确认"]["maturity"]=="outcome_supportive"
assert by["趋势确认"]["evidence_maturity"]["mature_n"]==10

states=cl.method_states(method)
assert states["仓位与加减仓"]["state"]=="direct_developing"
assert states["Sell Put"]["state"]=="context_only"
assert states["趋势确认"]["state"]=="outcome_supportive"
assert states["趋势确认"]["auto_weight_delta"]==0.0

# Controlled Learning must mirror the state while keeping all production actions locked.
policy=cl.build(
 replay={},
 outcome={},
 self_improvement={"candidates":[]},
 method=method,
 feedback={},
 previous={},
 now=datetime(2026,10,4,7,10,tzinfo=timezone.utc),
)
assert policy["version"]=="6.13.2"
assert policy["method_evidence_state"]["仓位与加减仓"]["state"]=="direct_developing"
assert policy["method_evidence_state"]["趋势确认"]["state"]=="outcome_supportive"
assert policy["method_evidence_state"]["趋势确认"]["auto_weight_delta"]==0.0
assert policy["production_mutation"] is False
assert policy["automatic_orders"] is False

print("PASS V6.13.2 method evidence-state single source / no auto weight / no production mutation")
