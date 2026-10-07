#!/usr/bin/env python3
"""Research-only Options Opportunity Context.

Purpose:
- rank a focused watch universe for live option-chain inspection;
- combine price/trend, Volume Profile support and volatility research;
- never turn incomplete context into a trade action.

The browser/private layer may later enrich a SCAN candidate with Thesis,
events, IV Rank/Percentile, skew, DTE, Delta, OI and Bid/Ask before surfacing
a strategy candidate.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MARKET=ROOT/"docs"/"data.json"
SUPPORT_VOL=ROOT/"docs"/"research"/"support_volatility_intelligence.json"
OUT=ROOT/"docs"/"research"/"options_opportunity_context.json"
UNIVERSE=["QQQ","SOFI","LITE","IREN","NVDA","TSLA"]
STRATEGY_PREFERENCES={
    "LITE":{"primary":"SELL_PUT","source":"user_strategy_preference","note":"High-volatility name; prioritize premium-selling research before long-call expressions."},
    "NVDA":{"primary":"SELL_PUT","source":"user_strategy_preference","note":"Prioritize cash-secured Sell Put research; live chain, support and event gates still apply."},
}


def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}


def market_row(data,symbol):
    return (data.get("stocks") or {}).get(symbol) or (data.get("core") or {}).get(symbol) or (data.get("index") or {}).get(symbol) or {}


def finite(v):
    try:
        x=float(v)
        return x if x==x else None
    except Exception:return None


def build_symbol(symbol,market,svi):
    m=market_row(market,symbol)
    v=(svi.get("records") or {}).get(symbol) or {}
    if not m or v.get("status")!="ok":
        return {
            "symbol":symbol,"status":"data_incomplete","state":"data_incomplete","scan_priority":"blocked",
            "scan_lanes":[],"research_modes":[],"trade_action":None,"production_effect":"none",
            "missing":[x for x in ["market" if not m else None,"support_volatility" if v.get("status")!="ok" else None] if x],
        }

    price=finite(m.get("close"))
    rsi=finite(m.get("rsi"))
    dist200=finite(m.get("dist_200ma"))
    drawdown=finite(m.get("window_drawdown"))
    sr=v.get("support_resistance") or {}
    vol=v.get("volatility") or {}
    sup=sr.get("nearest_support") or {}
    sup_dist=finite(sup.get("distance_pct"))
    strength=str(sup.get("strength") or "")
    rv20=finite(vol.get("rv20_ann_pct"))
    rv60=finite(vol.get("rv60_ann_pct"))
    g=vol.get("garch20") or {}
    garch=finite(g.get("ann_vol_pct_avg")) if g.get("status")=="ok" else None

    near_support=sup_dist is not None and -4.0<=sup_dist<=0.5 and strength in {"强","超强"}
    forecast_expanding=(garch is not None and rv20 is not None and garch>=rv20*1.10)
    high_realized=(rv60 is not None and rv60>=45.0)
    trend_constructive=(dist200 is not None and dist200>=-0.03 and rsi is not None and 42<=rsi<=72)
    oversold=(rsi is not None and rsi<35)
    structurally_weak=(dist200 is not None and dist200<-0.12)

    preference=STRATEGY_PREFERENCES.get(symbol) or {}
    lanes=[]; reasons=[]
    if preference.get("primary")=="SELL_PUT":
        lanes.append("SELL_PUT_CHAIN_SCAN")
        reasons.append("preferred_sell_put_research")
    if near_support and (forecast_expanding or high_realized):
        lanes.append("SELL_PUT_CHAIN_SCAN")
        reasons.append("strong_support_plus_volatility")
    if trend_constructive and not high_realized:
        lanes.append("LEAPS_CALL_CHAIN_SCAN")
        reasons.append("constructive_trend_plus_non_extreme_realized_vol")
    elif trend_constructive:
        lanes.append("LEAPS_CALL_IV_CHECK")
        reasons.append("constructive_trend_but_volatility_elevated")
    if oversold and near_support:
        lanes.append("REVERSAL_CALL_RESEARCH")
        reasons.append("oversold_near_support")
    if structurally_weak:
        reasons.append("below_200ma_risk")

    score=0
    if near_support:score+=3
    if forecast_expanding:score+=2
    if high_realized:score+=1
    if trend_constructive:score+=2
    if oversold:score+=1
    if structurally_weak:score-=2
    priority="high" if score>=5 else "medium" if score>=2 else "low"

    research_modes=[]
    if "SELL_PUT_CHAIN_SCAN" in lanes:research_modes.append("SELL_PUT_SCREEN")
    if any(x in lanes for x in ("LEAPS_CALL_CHAIN_SCAN","LEAPS_CALL_IV_CHECK","REVERSAL_CALL_RESEARCH")):research_modes.append("LEAPS_SCREEN")

    return {
        "symbol":symbol,
        "status":"scan_context_ready" if lanes else "context_only",
        "state":"chain_scan_candidate" if lanes else "context_only",
        "scan_priority":priority,
        "strategy_preference":preference or None,
        "scan_lanes":list(dict.fromkeys(lanes)),
        "research_modes":research_modes,
        "nearest_support":sup or None,
        "rv20_ann_pct":rv20,
        "rv60_ann_pct":rv60,
        "garch20":g,
        "context":{
            "price":price,"rsi14":rsi,"dist_200ma":dist200,"window_drawdown":drawdown,
            "nearest_support":sup or None,
            "rv20_ann_pct":rv20,"rv60_ann_pct":rv60,"garch20_ann_pct":garch,
            "near_strong_support":near_support,
            "forecast_vol_expanding":forecast_expanding,
            "trend_constructive":trend_constructive,
            "structurally_weak":structurally_weak,
        },
        "reasons":reasons,
        "required_before_strategy_candidate":[
            "thesis_intact_or_explicit_index_case",
            "live_option_chain",
            "iv_rank_or_percentile",
            "event_risk",
            "bid_ask_liquidity",
            "dte_delta_contract_fit",
        ],
        "semantic_boundary":"research_chain_scan_not_trade_action",
        "trade_action":None,
        "production_effect":"none",
    }


def build(market=None,svi=None,now=None):
    market=market if market is not None else load(MARKET)
    svi=svi if svi is not None else load(SUPPORT_VOL)
    now=now or datetime.now(timezone.utc)
    rows=[build_symbol(s,market,svi) for s in UNIVERSE]
    order={"high":3,"medium":2,"low":1,"blocked":0}
    rows.sort(key=lambda x:(-order.get(x.get("scan_priority"),0),UNIVERSE.index(x["symbol"])))
    records={x["symbol"]:x for x in rows}
    ranked=[x["symbol"] for x in rows if x.get("status")=="scan_context_ready"]
    return {
        "version":"options-opportunity-context-1.1",
        "generated_at":now.isoformat(),
        "universe":UNIVERSE,
        "ranked_scan_order":ranked,
        "records":records,
        "records_list":rows,
        "guardrails":[
            "This artifact ranks live-chain research only; it is not a trade recommendation.",
            "No SELL PUT/LEAPS candidate may be promoted without Thesis/index-case, IV context, event risk and liquidity checks.",
            "Missing inputs fail closed. No automatic order, sizing or Production Rule mutation.",
        ],
    }


def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "universe":len(out["records"]),
        "high":sum(1 for x in out["records"].values() if x["scan_priority"]=="high"),
        "scan_candidates":sum(1 for x in out["records"].values() if x["scan_lanes"]),
    },ensure_ascii=False))


if __name__=="__main__":main()
