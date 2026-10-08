from pathlib import Path
import tempfile,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import support_volatility_outcome_memory as m

idx=pd.bdate_range("2026-01-02",periods=35)
df=pd.DataFrame({
 "open":[100+i*0.1 for i in range(35)],
 "high":[101+i*0.1 for i in range(35)],
 "low":[99+i*0.1 for i in range(35)],
 "close":[100+i*0.1 for i in range(35)],
},index=idx)
asof=str(idx[5].date())
current={"generated_at":"2026-01-10T00:00:00Z","records":{"ABC":{
 "status":"ok","as_of":asof,
 "support_resistance":{"current_price":100.5,"nearest_support":{"low":99,"high":101,"strength":"强","window":"90D"},"nearest_resistance":None},
 "volatility":{"rv20_ann_pct":20,"rv60_ann_pct":25,"garch20":{"status":"ok","ann_vol_pct_avg":22}}
}}}

with tempfile.TemporaryDirectory() as td:
    old_obs,old_out,old_summary=m.OBS_DIR,m.OUTCOME_DIR,m.OUT
    m.OBS_DIR=Path(td)/"obs";m.OUTCOME_DIR=Path(td)/"out";m.OUT=Path(td)/"summary.json"
    try:
        out=m.run(current,{"ABC":df})
        assert out["counts"]["observations"]==1
        assert out["counts"]["mature20"]==1
        assert out["counts"]["outcomes_added"]==1
        assert out["metrics"]["garch_mae_pct_points"] is not None
        again=m.run(current,{"ABC":df})
        assert again["counts"]["observations_added"]==0
        assert again["counts"]["outcomes_added"]==0
    finally:
        m.OBS_DIR,m.OUTCOME_DIR,m.OUT=old_obs,old_out,old_summary

print("PASS support/GARCH observation to mature outcome memory")
