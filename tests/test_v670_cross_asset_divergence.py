import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ca",ROOT/"scripts"/"cross_asset_divergence_engine.py")
ca=importlib.util.module_from_spec(spec);spec.loader.exec_module(ca)

dash={
 "updated":"2026-10-02T21:30:00Z",
 "market_regime":{
   "dist_52w_high":-0.01,
   "conditions":[
     {"key":"20天宽度","val":0.28},
     {"key":"50天宽度","val":0.31},
     {"key":"200天宽度","val":0.47},
   ]
 },
 "overview_charts":{
   "SPY":[{"d":f"2026-09-{i:02d}","c":700+i} for i in range(1,30)]
          +[{"d":f"2026-10-{i:02d}","c":729+i} for i in range(1,31)]
          +[{"d":f"2026-11-{i:02d}","c":759+i} for i in range(1,31)]
 },
 "index":{"SPY":{"date":"2026-09-01","close":701}}
}
macro={"series":{
 "DGS10":{"latest":{"value":5.30,"date":"2026-10-02"},"changes":{"20":0.35}},
 "DFII10":{"latest":{"value":2.45,"date":"2026-10-02"},"changes":{"20":0.20}},
 "BAMLH0A0HYM2":{"latest":{"value":3.24,"date":"2026-10-02"},"changes":{"20":0.30}},
 "VIXCLS":{"latest":{"value":17.2,"date":"2026-10-02"},"changes":{"20":0.5}},
 "NFCI":{"latest":{"value":-0.40,"date":"2026-09-25"},"changes":{"20":0.02}},
}}
out=ca.build(dash,macro)
assert out["version"]=="6.7.0"
assert out["level"]=="high"
assert out["high_hits"]>=3
hits={x["key"]:x for x in out["signals"]}
assert hits["rates_pressure"]["hit"] is True
assert hits["real_yield_pressure"]["hit"] is True
assert hits["credit_widening"]["hit"] is True
assert hits["breadth_divergence"]["hit"] is True
assert hits["financial_conditions_cushion"]["hit"] is True
assert out["guardrail"].startswith("跨资产背离")

hist={"records":[{"as_of":"2026-09-01","anchor_spy":701.0,"level":"high","outcomes":{}}]}
m=ca.mature_history(hist,dash)
row=m["records"][0]
assert "5" in row["outcomes"]
assert "20" in row["outcomes"]
assert row["outcomes"]["5"]["return"]>0
print("PASS V6.7 cross-asset divergence")
