import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bt",ROOT/"scripts"/"backtest_trend_pulse.py")
bt=importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)

# deterministic synthetic OHLCV with regime changes; validates causal plumbing and output schema.
rng=np.random.default_rng(7)
n=420
idx=pd.bdate_range("2024-01-02", periods=n)
segments=np.r_[np.linspace(100,75,80),np.linspace(75,135,120),np.linspace(135,112,55),np.linspace(112,170,100),np.linspace(170,130,65)]
close=segments*(1+rng.normal(0,0.008,n))
open_=close*(1+rng.normal(0,0.004,n))
high=np.maximum(open_,close)*(1+np.abs(rng.normal(0.008,0.003,n)))
low=np.minimum(open_,close)*(1-np.abs(rng.normal(0.008,0.003,n)))
df=pd.DataFrame({"open":open_,"high":high,"low":low,"close":close,"volume":rng.integers(1_000_000,4_000_000,n)},index=idx)
sc=bt.build_daily_pulse(df)
assert len(sc)==n
assert sc["pulse"].dropna().between(-100,100).all()
ev=bt.event_rows("TEST",sc)
assert all(e["state_key"] in {"trend_start","second_start","trend_fade"} for e in ev)
assert all("ret_20d" in e for e in ev)
base=bt.eligible_baseline(sc)
assert all(h in base for h in bt.HORIZONS)
print("trend pulse backtest plumbing: passed", len(ev), "events")
