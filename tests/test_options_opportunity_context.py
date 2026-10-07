from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ooc",ROOT/"scripts"/"options_opportunity_context.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

market={
 "core":{"QQQ":{"close":700,"rsi":55,"dist_200ma":0.05,"window_drawdown":-0.08}},
 "stocks":{
   "SOFI":{"close":16,"rsi":33,"dist_200ma":-0.05,"window_drawdown":-0.35},
   "LITE":{"close":1000,"rsi":68,"dist_200ma":0.20,"window_drawdown":-0.02},
   "IREN":{"close":40,"rsi":48,"dist_200ma":-0.02,"window_drawdown":-0.30},
   "NVDA":{"close":240,"rsi":62,"dist_200ma":0.18,"window_drawdown":-0.03},
   "TSLA":{"close":380,"rsi":58,"dist_200ma":-0.15,"window_drawdown":-0.20},
 }
}
def rec(support_dist,strength="强",rv20=30,rv60=40,garch=36):
 return {"status":"ok","support_resistance":{"nearest_support":{"low":90,"high":95,"strength":strength,"distance_pct":support_dist}},"volatility":{"rv20_ann_pct":rv20,"rv60_ann_pct":rv60,"garch20":{"status":"ok","ann_vol_pct_avg":garch}}}
svi={"records":{
 "QQQ":rec(-2,rv20=15,rv60=18,garch=17),
 "SOFI":rec(-1,"超强",rv20=35,rv60=55,garch=50),
 "LITE":rec(-12,rv20=70,rv60=90,garch=75),
 "IREN":rec(0,"超强",rv20=45,rv60=70,garch=55),
 "NVDA":rec(-6,rv20=28,rv60=30,garch=30),
 "TSLA":rec(-3,"强",rv20=50,rv60=60,garch=55),
}}

out=m.build(market,svi)
rows=out["records"]
assert set(rows)==set(m.UNIVERSE)
assert out["ranked_scan_order"]
assert all(rows[s]["status"] in {"scan_context_ready","context_only"} for s in rows)
assert "SELL_PUT_CHAIN_SCAN" in rows["IREN"]["scan_lanes"]
assert "SELL_PUT_SCREEN" in rows["IREN"]["research_modes"]
assert "SELL_PUT_CHAIN_SCAN" in rows["SOFI"]["scan_lanes"]
assert rows["LITE"]["strategy_preference"]["primary"]=="SELL_PUT"
assert "SELL_PUT_CHAIN_SCAN" in rows["LITE"]["scan_lanes"]
assert "SELL_PUT_SCREEN" in rows["LITE"]["research_modes"]
assert rows["NVDA"]["strategy_preference"]["primary"]=="SELL_PUT"
assert "SELL_PUT_CHAIN_SCAN" in rows["NVDA"]["scan_lanes"]
assert "SELL_PUT_SCREEN" in rows["NVDA"]["research_modes"]
assert "LEAPS_CALL_CHAIN_SCAN" in rows["QQQ"]["scan_lanes"]
assert "LEAPS_SCREEN" in rows["QQQ"]["research_modes"]
assert rows["TSLA"]["context"]["structurally_weak"] is True
assert all(x["trade_action"] is None for x in rows.values())
assert all(x["production_effect"]=="none" for x in rows.values())
assert all("live_option_chain" in x["required_before_strategy_candidate"] for x in rows.values())

bad=m.build(market,{"records":{}})
assert all(x["scan_priority"]=="blocked" for x in bad["records"].values())
assert all(x["trade_action"] is None for x in bad["records"].values())
assert bad["ranked_scan_order"]==[]
print("PASS options opportunity research context / no trade action / fail closed")
