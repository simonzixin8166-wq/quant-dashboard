from pathlib import Path
import tempfile,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import options_opportunity_outcome_memory as m

idx=pd.bdate_range("2026-01-02",periods=35)
df=pd.DataFrame({
 "open":[100+i for i in range(35)],
 "high":[101+i for i in range(35)],
 "low":[99+i for i in range(35)],
 "close":[100+i for i in range(35)],
},index=idx)
doc={"generated_at":"2026-01-05T00:00:00Z","records":{"ABC":{
 "state":"chain_scan_candidate","status":"scan_context_ready","scan_priority":"high",
 "scan_lanes":["SELL_PUT_CHAIN_SCAN"],"research_modes":["SELL_PUT_SCREEN"],
 "reasons":["strong_support_plus_volatility"],
 "required_before_strategy_candidate":["live_option_chain"],
 "context":{"price":101.0,"rsi14":40,"near_strong_support":True,"forecast_vol_expanding":True,"trend_constructive":False,"structurally_weak":False}
}}}

with tempfile.TemporaryDirectory() as td:
    old_obs,old_out,old_summary=m.OBS,m.OUTCOMES,m.OUT
    m.OBS=Path(td)/"obs";m.OUTCOMES=Path(td)/"out";m.OUT=Path(td)/"summary.json"
    try:
        out=m.run(doc,{"ABC":df})
        assert out["counts"]["observations"]==1
        assert out["counts"]["matured"]==2
        assert out["counts"]["outcomes_added"]==2
        again=m.run(doc,{"ABC":df})
        assert again["counts"]["observations_added"]==0
        assert again["counts"]["outcomes_added"]==0
        assert again["horizons"]["5"]["n"]==1
        assert again["horizons"]["20"]["n"]==1
    finally:
        m.OBS,m.OUTCOMES,m.OUT=old_obs,old_out,old_summary
print("PASS options opportunity observation/outcome memory")
