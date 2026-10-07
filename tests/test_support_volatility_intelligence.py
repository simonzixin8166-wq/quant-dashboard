from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("svi",ROOT/"scripts"/"support_volatility_intelligence.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

# Deterministic synthetic OHLCV with enough history for all core calculations.
n=800
idx=pd.bdate_range("2023-01-02",periods=n)
base=np.linspace(20,40,n)+np.sin(np.arange(n)/18)*2
frame=pd.DataFrame({
    "Open":base-0.2,
    "High":base+1.0,
    "Low":base-1.0,
    "Close":base,
    "Volume":np.where((np.arange(n)%60)<15,2_000_000,700_000),
},index=idx)

assert m.adaptive_bin_size(25)==0.25
assert m.adaptive_bin_size(700) in {5.0,10.0}
profile=m.compute_volume_profile(frame,0.5,252)
assert not profile.empty
assert {"中","强","超强"} & set(profile["strength"])

support=m.support_snapshot(frame)
assert support["current_price"]>0
assert len(support["windows"])==4
assert support["adaptive_bin_size"]>0
assert support["nearest_support"] is not None
assert support["nearest_resistance"] is not None

rv=m.realized_volatility(frame)
assert rv["rv20_ann_pct"] is not None
assert rv["rv60_ann_pct"] is not None

def fake_fetch(_symbol):
    return frame

out=m.build(["QQQ","SOFI"],fetcher=fake_fetch)
assert out["universe"]==["QQQ","SOFI"]
assert all(out["records"][s]["status"]=="ok" for s in out["universe"])
assert all(out["records"][s]["trade_action"] is None for s in out["universe"])
assert all(out["records"][s]["decision_effect"]=="research_only" for s in out["universe"])

# Data failure must fail closed and never invent support/volatility.
def bad_fetch(_symbol):
    raise RuntimeError("offline")
bad=m.build(["LITE"],fetcher=bad_fetch)
assert bad["records"]["LITE"]["status"]=="unavailable"
assert bad["records"]["LITE"]["decision_effect"]=="fail_closed"
assert bad["records"]["LITE"]["trade_action"] is None

print("PASS support/volatility research-only engine and fail-closed contract")
