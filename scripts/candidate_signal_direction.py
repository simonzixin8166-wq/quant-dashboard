#!/usr/bin/env python3
"""Candidate Signal Direction Governance v1.0.

Defines research/evaluation direction for compiled Candidate signals without
mapping them to BUY/SELL actions.

Principles:
- direction comes only from machine-reproducible condition semantics;
- all directional conditions must agree;
- mixed/unknown direction fails closed;
- direction is for outcome scoring only, never order/action semantics;
- no Promotion/Production mutation.
"""
from __future__ import annotations

DIRECTION_BY_CONDITION={
    "price_above_ma20":"bullish",
    "ma20_hold_two_sessions":"bullish",
    "price_above_ma50":"bullish",
    "ma50_hold_two_sessions":"bullish",
    "price_above_ma200":"bullish",
    "ma200_hold_two_sessions":"bullish",
    "price_below_ma20":"bearish",
    "price_below_ma50":"bearish",
    "price_below_ma200":"bearish",
    "macd_hist_positive":"bullish",
    "ppo_above_signal":"bullish",
    "ppo_hist_positive":"bullish",
    "supertrend_bullish":"bullish",
}
VERSION="1.0"

def govern(candidate):
    conditions=[x for x in (candidate.get("conditions") or []) if isinstance(x,dict)]
    votes=[]
    basis=[]
    unresolved=[]
    for cond in conditions:
        cid=str(cond.get("condition_id") or "")
        if not cond.get("machine_ready"):
            unresolved.append(cid or "unknown")
            continue
        d=DIRECTION_BY_CONDITION.get(cid)
        if not d:
            unresolved.append(cid or "unknown")
            continue
        votes.append(d)
        basis.append({"condition_id":cid,"direction":d})
    uniq=sorted(set(votes))
    if unresolved:
        state="direction_unresolved"
        direction=None
        reason="one_or_more_conditions_lack_explicit_direction_semantics"
    elif len(uniq)==1 and votes:
        state="direction_governed"
        direction=uniq[0]
        reason=None
    elif len(uniq)>1:
        state="direction_conflict"
        direction=None
        reason="machine_ready_conditions_disagree_on_direction"
    else:
        state="direction_unresolved"
        direction=None
        reason="no_directional_machine_ready_condition"
    return {
        "version":VERSION,
        "state":state,
        "expected_direction":direction,
        "basis":basis,
        "unresolved_conditions":sorted(set(unresolved)),
        "reason":reason,
        "semantic_boundary":"research_outcome_direction_not_trade_action",
        "trade_action":None,
        "production_effect":"none",
        "promotion_effect":"none",
    }
