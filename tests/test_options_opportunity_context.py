from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ooc",ROOT/"scripts"/"options_opportunity_context.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

data={
 "core":{"QQQ":{"date":"2026-10-06","close":760,"rsi":55,"dist_200ma":0.12,"window_drawdown":-0.02}},
 "stocks":{
   "IREN":{"date":"2026-10-06","close":41,"rsi":42,"dist_200ma":-0.08,"window_drawdown":-0.40},
   "NVDA":{"date":"2026-10-06","close":239,"rsi":68,"dist_200ma":0.18,"window_drawdown":-0.03},
   "SOFI":{"date":"2026-10-06","close":15.7,"rsi":36,"dist_200ma":-0.16,"window_drawdown":-0.50},
   "LITE":{"date":"2026-10-06","close":1133,"rsi":72,"dist_200ma":0.50,"window_drawdown":-0.01},
   "TSLA":{"date":"2026-10-06","close":381,"rsi":60,"dist_200ma":-0.03,"window_drawdown":-0.23},
 }
}
def sv(status="ok",dist=-3,rv=50):
 return {
   "status":status,
   "as_of":"2026-10-06",
   "support_resistance":{"nearest_support":{"low":38,"high":40,"strength":"强","distance_pct":dist}},
   "volatility":{"rv20_ann_pct":rv,"rv60_ann_pct":45,"garch20":{"status":"ok","ann_vol_pct_avg":60}}
 }
svdoc={"records":{s:sv() for s in m.UNIVERSE}}
out=m.build(data,svdoc)
assert out["universe"]==m.UNIVERSE
assert out["records"]["QQQ"]["required_runtime_gates"][0]=="formal_core_strategy_and_market_regime"
assert out["records"]["IREN"]["required_runtime_gates"][0]=="private_thesis_and_invalidation_required"
assert "SELL_PUT_SCREEN" in out["records"]["IREN"]["research_modes"]
assert "LEAPS_SCREEN" in out["records"]["QQQ"]["research_modes"]
assert out["records"]["IREN"]["final_strategy"] is None
assert out["records"]["IREN"]["trade_action"] is None
assert out["records"]["IREN"]["production_effect"]=="none"

# Missing public evidence remains incomplete and cannot fabricate a strategy.
bad=m.build(data,{"records":{"QQQ":{"status":"unavailable"}}})
assert bad["records"]["QQQ"]["status"]=="data_incomplete"
assert bad["records"]["QQQ"]["final_strategy"] is None
assert bad["records"]["QQQ"]["trade_action"] is None

print("PASS focused options opportunity context / private-thesis boundary / no trade action")
