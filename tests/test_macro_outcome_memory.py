from pathlib import Path
import tempfile,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import macro_outcome_memory as m

idx=pd.bdate_range("2026-01-02",periods=90)
spy=pd.DataFrame({"open":[100+i*.2 for i in range(90)],"high":[101+i*.2 for i in range(90)],"low":[99+i*.2 for i in range(90)],"close":[100+i*.2 for i in range(90)]},index=idx)
doc={"generated_at":"2026-01-10T00:00:00Z","as_of":str(idx[5].date()),"point_in_time_capable":True,
"regime":{"rates_regime":"RISING","real_yield_regime":"RISING","yield_curve":"NORMAL","inflation_regime":"STABLE","credit_regime":"EASY","financial_conditions":"LOOSE","macro_risk_score":34},
"quality":{"confidence":"HIGH"}}
with tempfile.TemporaryDirectory() as td:
 old_obs,old_outcomes,old_out=m.OBS,m.OUTCOMES,m.OUT
 m.OBS=Path(td)/"obs.jsonl";m.OUTCOMES=Path(td)/"outcomes.jsonl";m.OUT=Path(td)/"summary.json"
 try:
  out=m.run(doc,{"SPY":spy})
  assert out["counts"]["observations"]==1
  assert out["counts"]["outcomes"]==3
  again=m.run(doc,{"SPY":spy})
  assert again["counts"]["observations_added"]==0
  assert again["counts"]["outcomes_added"]==0
 finally:
  m.OBS,m.OUTCOMES,m.OUT=old_obs,old_outcomes,old_out
print("PASS macro regime point-in-time outcome memory")
