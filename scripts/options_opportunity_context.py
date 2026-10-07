#!/usr/bin/env python3
"""Research-only Options Opportunity Context.

Builds a focused scan context for QQQ/SOFI/LITE/IREN/NVDA/TSLA from public
market structure plus Support & Volatility Intelligence. It does NOT read
private Thesis notes and does NOT fabricate option-chain metrics.

Final strategy candidates require runtime private/formal thesis gating plus
real option-chain IV/Delta/Bid-Ask/event checks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs"/"data.json"
SV=ROOT/"docs"/"research"/"support_volatility_intelligence.json"
OUT=ROOT/"docs"/"research"/"options_opportunity_context.json"
UNIVERSE=["QQQ","SOFI","LITE","IREN","NVDA","TSLA"]


def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default


def market_row(data,symbol):
    return (data.get("stocks") or {}).get(symbol) or (data.get("core") or {}).get(symbol) or (data.get("index") or {}).get(symbol) or {}


def build_symbol(symbol,row,sv):
    support=(sv.get("support_resistance") or {}).get("nearest_support")
    volatility=sv.get("volatility") or {}
    garch=(volatility.get("garch20") or {})
    rsi=row.get("rsi"); dist=row.get("dist_200ma"); dd=row.get("window_drawdown")
    try:rsi=float(rsi)
    except Exception:rsi=None
    try:dist=float(dist)
    except Exception:dist=None
    try:dd=float(dd)
    except Exception:dd=None
    support_dist=support.get("distance_pct") if isinstance(support,dict) else None

    modes=[]
    reasons=[]
    # This is scan routing only, not strategy advice.
    if support_dist is not None and -8.0<=float(support_dist)<=0:
        modes.append("SELL_PUT_SCREEN"); reasons.append("near_volume_profile_support")
    if dd is not None and dd<=-0.20:
        if "SELL_PUT_SCREEN" not in modes:modes.append("SELL_PUT_SCREEN")
        reasons.append("material_drawdown")
    if dist is not None and dist>-0.05 and (rsi is None or rsi<75):
        modes.append("LEAPS_SCREEN"); reasons.append("long_term_structure_not_broken")
    if rsi is not None and rsi>=75:
        reasons.append("overbought_guard")
    if not modes:
        modes=["WATCH_ONLY"]

    score=0
    if support_dist is not None and -5<=float(support_dist)<=0:score+=30
    if dd is not None and dd<=-0.20:score+=20
    if rsi is not None and rsi<=45:score+=15
    if dist is not None and dist>-0.05:score+=10
    if garch.get("status")=="ok":score+=10

    thesis_gate="formal_core_strategy_and_market_regime" if symbol=="QQQ" else "private_thesis_and_invalidation_required"
    return {
        "symbol":symbol,
        "status":"scan_context_ready" if row and sv.get("status")=="ok" else "data_incomplete",
        "as_of":row.get("date") or sv.get("as_of"),
        "spot":row.get("close"),
        "rsi14":rsi,
        "dist_200ma":dist,
        "window_drawdown":dd,
        "nearest_support":support,
        "rv20_ann_pct":volatility.get("rv20_ann_pct"),
        "rv60_ann_pct":volatility.get("rv60_ann_pct"),
        "garch20":garch,
        "research_modes":list(dict.fromkeys(modes)),
        "scan_priority_score":score,
        "scan_reasons":list(dict.fromkeys(reasons)),
        "required_runtime_gates":[
            thesis_gate,
            "real_option_chain_required",
            "iv_rank_or_relative_iv_required",
            "bid_ask_liquidity_required",
            "event_risk_required",
            "position_risk_budget_required",
        ],
        "final_strategy":None,
        "trade_action":None,
        "production_effect":"none",
    }


def build(data=None,svdoc=None,now=None):
    data=data if data is not None else load(DATA,{})
    svdoc=svdoc if svdoc is not None else load(SV,{})
    now=now or datetime.now(timezone.utc)
    svrows=svdoc.get("records") or {}
    rows={}
    for symbol in UNIVERSE:
        rows[symbol]=build_symbol(symbol,market_row(data,symbol),svrows.get(symbol) or {})
    ranked=sorted(rows,key=lambda s:(rows[s]["status"]=="scan_context_ready",rows[s]["scan_priority_score"]),reverse=True)
    return {
        "version":"options-opportunity-context-1",
        "generated_at":now.isoformat(),
        "universe":UNIVERSE,
        "ranked_scan_order":ranked,
        "records":rows,
        "guardrails":[
            "Research scan context only; never a BUY/SELL or option-entry instruction.",
            "Private Thesis notes are evaluated only at authenticated runtime and never copied into this public artifact.",
            "QQQ uses formal core strategy + market regime instead of a company Thesis gate.",
            "Real option-chain IV/Delta/Bid-Ask and event risk are mandatory before any strategy candidate is shown.",
            "Missing support/volatility/chain data fails closed.",
        ],
    }


def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"universe":len(out["universe"]),"ready":sum(1 for x in out["records"].values() if x["status"]=="scan_context_ready"),"ranked":out["ranked_scan_order"]},ensure_ascii=False))


if __name__=="__main__":
    main()
