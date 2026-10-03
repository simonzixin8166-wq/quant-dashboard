import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rm",ROOT/"scripts"/"regime_combination_memory.py")
rm=importlib.util.module_from_spec(spec);spec.loader.exec_module(rm)

dash={
 "spy_date":"2026-10-02",
 "market_indicators":{"vix":{"close":16.5}},
 "index":{"SPY":{"close":770.0}},
 "overview_charts":{"SPY":[{"d":f"2026-09-{i:02d}","c":700+i} for i in range(1,30)]
                         +[{"d":f"2026-10-{i:02d}","c":729+i} for i in range(1,31)]
                         +[{"d":f"2026-11-{i:02d}","c":759+i} for i in range(1,31)]}
}
cross={"level":"high","label":"高位跨资产背离","risk_hits":4}
breadth={"level":"fragile","label":"参与度脆弱 · 权重股主导","participation_score":31.5,"combination_key":"B20_LOW|B50_LOW|SPY_RSP_GAP"}
history={"records":[
 {"as_of":"2026-09-01","anchor_spy":701.0,"state_id":"CROSS_HIGH|BREADTH_FRAGILE|VIX_LOW","outcomes":{}}
]}
m=rm.mature_history(history,dash)
out=rm.build(dash,cross,breadth,m)
assert out["version"]=="6.8.0"
assert out["level"]=="high"
assert out["state_id"]=="CROSS_HIGH|BREADTH_FRAGILE|VIX_LOW"
assert out["historical_matches"]["total"]==1
assert out["historical_matches"]["mature"]["5"]["n"]==1
assert out["historical_matches"]["mature"]["20"]["n"]==1

out2=rm.build(dash,{"level":"low"},{"level":"healthy","participation_score":70},{})
assert out2["level"]=="low"
print("PASS V6.8 regime combination memory")
