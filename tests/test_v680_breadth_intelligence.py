import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bi",ROOT/"scripts"/"breadth_intelligence_engine.py")
bi=importlib.util.module_from_spec(spec);spec.loader.exec_module(bi)

left=[{"d":f"2026-08-{i:02d}","c":100+i} for i in range(1,29)]
left += [{"d":f"2026-09-{i:02d}","c":128+i} for i in range(1,29)]
left += [{"d":f"2026-10-{i:02d}","c":156+i} for i in range(1,10)]
right=[{"d":x["d"],"c":x["c"]*(1+0.0008*n)} for n,x in enumerate(left)]
rel=bi.relative_pair(left,right,"RSP","SPY")
assert rel["available"] is True
assert rel["pair"]=="RSP/SPY"
assert rel["chg20"]<0
assert rel["signal"]=="weak"

dash={
 "spy_date":"2026-10-02",
 "index":{"SPY":{"close":764.0}},
 "raw_breadth":{
   "status":"ok","date":"2026-10-02","coverage":501,"universe":503,
   "b20":0.26,"b50":0.24,"b200":0.45,"slope_10d":0.06,
   "advance_pct":0.39,"decline_pct":0.59,"ad_net_pct":-0.20,
   "ad_line_20d":-2.4,"ad_line_60d":-3.1,
   "new_high_52w_pct":0.06,"near_high_52w_pct":0.22,"new_low_52w_pct":0.02,
 }
}
cross={"signals":[
 {"key":"equity_near_high","hit":True},
 {"key":"rates_pressure","hit":True},
 {"key":"real_yield_pressure","hit":True},
 {"key":"credit_widening","hit":True},
 {"key":"vix_disconnect","hit":True},
]}
relative={
 "rsp_spy":rel,
 "qqqe_qqq":{"available":True,"pair":"QQQE/QQQ","chg20":-0.02,"chg60":-0.03,"vs_ma50":-0.01,"signal":"weak"}
}
history={"records":[]}
out=bi.build(dash,cross,relative,history)
assert out["version"]=="6.8.0"
assert out["level"]=="high"
assert out["flags"]["BREADTH_WEAK"] is True
assert out["flags"]["AD_NEGATIVE"] is True
assert out["flags"]["NEW_HIGHS_THIN"] is True
assert out["flags"]["EQUAL_WEIGHT_WEAK"] is True
assert "EQUITY_NEAR_HIGH" in out["fingerprint"]
assert out["guardrail"].startswith("Breadth Intelligence")

spy=[{"d":f"2026-01-{i:02d}","c":100+i} for i in range(1,29)]
# Use deterministic sequential dates independent of real calendar validation.
spy=[{"d":f"2026-{1+(i//28):02d}-{1+(i%28):02d}","c":100+i} for i in range(100)]
hist={"records":[{"as_of":spy[0]["d"],"anchor_spy":100.0,"level":"high","fingerprint":"X","outcomes":{}}]}
m=bi.mature_history(hist,spy)
row=m["records"][0]
for h in ("5","20","60"):
    assert h in row["outcomes"]
    assert row["outcomes"][h]["return"]>0
    assert row["outcomes"][h]["mae"]>0
    assert row["outcomes"][h]["mfe"]>=row["outcomes"][h]["mae"]

same=[]
for _ in range(20):
    same.append({"fingerprint":out["fingerprint"],"level":"high","outcomes":{"20":{"return":-0.03,"mae":-0.06,"mfe":0.01}}})
out2=bi.build(dash,cross,relative,{"records":same})
assert out2["current_combination_history"]["20"]["n"]==20
assert out2["current_combination_history"]["20"]["avg_return"]==-0.03
assert out2["current_combination_history"]["20"]["avg_mae"]==-0.06
print("PASS V6.8 Breadth Intelligence / Regime Combination Memory")
