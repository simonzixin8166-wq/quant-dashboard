import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bi",ROOT/"scripts"/"breadth_intelligence_engine.py")
bi=importlib.util.module_from_spec(spec);spec.loader.exec_module(bi)

dash={
 "spy_date":"2026-10-02",
 "raw_breadth":{"status":"ok","date":"2026-10-02","b20":0.25,"b50":0.30,"b200":0.43,"slope_10d":-0.12,"coverage":500,"universe":503},
 "breadth_proxies":{
   "SPY":{"status":"ok","returns":{"20":0.08}},
   "RSP":{"status":"ok","returns":{"20":0.02}},
   "QQQ":{"status":"ok","returns":{"20":0.10}},
   "QQQE":{"status":"ok","returns":{"20":0.03}},
 },
 "index":{"SPY":{"close":770.0}},
 "overview_charts":{"SPY":[{"d":f"2026-09-{i:02d}","c":700+i} for i in range(1,30)]
                         +[{"d":f"2026-10-{i:02d}","c":729+i} for i in range(1,31)]
                         +[{"d":f"2026-11-{i:02d}","c":759+i} for i in range(1,31)]}
}
out=bi.build(dash)
assert out["version"]=="6.8.0"
assert out["level"]=="fragile"
assert out["participation_score"]<40
assert out["metrics"]["spy_minus_rsp_20d"]>0.05
assert out["metrics"]["qqq_minus_qqqe_20d"]>0.05
assert "SPY_RSP_GAP" in out["combination_key"]
assert "QQQ_QQQE_GAP" in out["combination_key"]
assert any(x["key"]=="sp500_concentration" and x["hit"] for x in out["signals"])

hist={"records":[{"as_of":"2026-09-01","anchor_spy":701.0,"level":"fragile","outcomes":{}}]}
m=bi.mature_history(hist,dash)
assert "5" in m["records"][0]["outcomes"]
assert "20" in m["records"][0]["outcomes"]

healthy={
 "raw_breadth":{"status":"ok","date":"2026-10-02","b20":0.70,"b50":0.68,"b200":0.62,"slope_10d":0.10},
 "breadth_proxies":{
   "SPY":{"status":"ok","returns":{"20":0.05}},"RSP":{"status":"ok","returns":{"20":0.045}},
   "QQQ":{"status":"ok","returns":{"20":0.06}},"QQQE":{"status":"ok","returns":{"20":0.055}},
 }
}
out2=bi.build(healthy)
assert out2["level"]=="healthy"
assert out2["risk_hits"]==0
print("PASS V6.8 Breadth Intelligence")
