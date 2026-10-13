#!/usr/bin/env python3
"""OPT-01 (#133 6138710630) — Sell Put / Covered Call management: Shadow decision comparison. NO ORDERS.

For one short option (one contract, one account) compare four paths with the same inputs:
  close_now (buy back) · hold_to_expiry · roll (only with a real quote for the new contract) · assigned/called away
and stress it (gap down/up, IV expansion, earnings / ex-dividend inside the DTE). Everything is a model
read with stated assumptions, never a verified win rate:
  - probabilities are Black–Scholes risk-neutral N(d2) estimates from the IV supplied, not frequencies;
  - without a real implied volatility the result is `model_inputs_incomplete`; a realised-vol figure may be
    shown only as `illustrative_rv_not_iv` and never drives a hint;
  - common practitioner heuristics (take profit at 50–80 % of premium, manage before the last week) are
    labelled `heuristic_unverified`;
  - private positions never enter the public repo: callers pass a position dict at runtime.
production_use=false, used_in_decision=false, automatic_orders=false.
"""
from __future__ import annotations
import math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_option_math import calc_option_greeks, norm_cdf  # noqa: E402

CONTRACT = 100
HEURISTICS = {"take_profit_captured": (0.50, 0.80), "gamma_zone_dte": 7}


def _bs(S, K, dte, sigma, kind, r=0.04):
    T = max(dte, 0) / 365.0
    g = calc_option_greeks(S, K, T, r, sigma, "Call" if kind == "call" else "Put")
    if T <= 0 or sigma <= 0:
        intrinsic = max(0.0, (S - K) if kind == "call" else (K - S))
        return {"price": intrinsic, "delta": None, "p_itm": 1.0 if intrinsic > 0 else 0.0}
    d2 = (math.log(S / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    p_itm = norm_cdf(d2) if kind == "call" else norm_cdf(-d2)
    return {"price": g["theo_price"], "delta": g["delta"], "p_itm": p_itm}


def dte_stage(dte):
    return ("1-3 DTE: gamma 风险最高，小幅波动即可改变是否被指派" if dte <= 3 else
            "4-10 DTE: 时间价值衰减快，但跳空风险仍集中" if dte <= 10 else
            "11-30 DTE: 管理窗口，剩余时间价值较多" if dte <= 30 else ">30 DTE: 时间价值衰减较慢")


def compare(pos, fees_per_contract=0.65, slippage=0.02):
    """pos: kind put|call, strike, premium_received (per share), mark (current ask to buy back, per share, optional),
    underlying, dte, iv (decimal, optional), rv (decimal, optional), shares_held (covered calls),
    earnings_date_within_dte (bool|None), ex_dividend_within_dte (bool|None), dividend (per share|None),
    roll_quote: {strike, dte, premium} (optional real quote)."""
    k, K, S, dte = pos["kind"], float(pos["strike"]), float(pos["underlying"]), int(pos["dte"])
    prem = float(pos["premium_received"])
    out = {"production_use": False, "used_in_decision": False, "automatic_orders": False,
           "kind": k, "covered": k == "call" and int(pos.get("shares_held") or 0) >= CONTRACT, "dte_stage": dte_stage(dte),
           "assumptions": {"model": "Black-Scholes, r=4%, European approximation; probabilities are risk-neutral estimates, not win rates",
                           "fees_per_contract": fees_per_contract, "slippage_per_share": slippage}}
    if k == "call" and not out["covered"]:
        out["warning"] = "uncovered call: unlimited upside risk — outside the owner's covered-call scope"
    iv = pos.get("iv")
    if iv is None:
        out["status"] = "model_inputs_incomplete"
        out["missing"] = ["implied_volatility"] + ([] if pos.get("mark") is not None else ["option_mark"])
        if pos.get("rv"):
            out["illustrative_rv_not_iv"] = _bs(S, K, dte, float(pos["rv"]), k)
        return out
    model = _bs(S, K, dte, float(iv), k)
    mark = float(pos["mark"]) if pos.get("mark") is not None else model["price"]
    out["mark_source"] = "quote" if pos.get("mark") is not None else "model_estimate_no_quote"
    intrinsic = max(0.0, (S - K) if k == "call" else (K - S))
    captured = (prem - mark) / prem if prem > 0 else None
    cost_close = (mark + slippage) * CONTRACT + fees_per_contract
    out["now"] = {"premium_captured_pct": None if captured is None else round(captured, 4), "mark": round(mark, 4),
                  "intrinsic": round(intrinsic, 4), "extrinsic_left": round(max(0.0, mark - intrinsic), 4),
                  "delta": None if model["delta"] is None else round(model["delta"], 4), "p_itm_at_expiry_model": round(model["p_itm"], 4)}
    out["paths"] = {
        "close_now": {"pnl_usd": round(prem * CONTRACT - cost_close, 2), "frees_capital_usd": K * CONTRACT if k == "put" else 0,
                      "residual_risk": "none after the buy-back fills"},
        "hold_to_expiry": {"max_additional_gain_usd": round(mark * CONTRACT, 2), "p_assignment_model": round(model["p_itm"], 4),
                           "residual_risk": "gap through the strike; assignment" + (" (early assignment risk around ex-dividend)" if k == "call" else "")},
        "assigned": ({"cash_needed_usd": K * CONTRACT, "effective_cost_basis": round(K - prem, 4),
                      "mark_to_market_vs_basis_usd": round((S - (K - prem)) * CONTRACT, 2)} if k == "put" else
                     {"shares_delivered": CONTRACT, "effective_sale_price": round(K + prem, 4),
                      "opportunity_cost_if_above_strike_usd": round(max(0.0, S - K) * CONTRACT, 2)}),
    }
    rq = pos.get("roll_quote")
    if rq:
        net = float(rq["premium"]) - mark - 2 * slippage
        out["paths"]["roll"] = {"to": rq, "net_credit_per_share": round(net, 4), "net_credit_usd": round(net * CONTRACT - 2 * fees_per_contract, 2),
                                "note": "roll only with a real quote for the new contract; a net debit is a cost, not a fix"}
    else:
        out["paths"]["roll"] = {"status": "quote_required", "note": "no real quote for the target contract — not modelled"}
    stress = {}
    for name, dS, dIV in (("gap_down_5pct", -0.05, 0), ("gap_down_10pct", -0.10, 0), ("gap_up_10pct", 0.10, 0), ("iv_plus_10pts", 0, 0.10)):
        m = _bs(S * (1 + dS), K, dte, float(iv) + dIV, k)
        stress[name] = {"option_value": round(m["price"], 4), "pnl_if_closed_usd": round((prem - m["price"]) * CONTRACT, 2),
                        "p_itm_model": round(m["p_itm"], 4)}
    out["stress"] = stress
    flags = []
    if pos.get("mark") is not None and max(mark, model["price"]) > 0 and abs(model["price"] - mark) / max(mark, model["price"]) > 0.25:
        flags.append(f"model/quote divergence: model {model['price']:.2f} vs quote {mark:.2f} — the IV input does not match the market; stress figures unreliable")
    if pos.get("earnings_date_within_dte"):
        flags.append("earnings inside DTE: gap risk dominates the model; IV crush after the event")
    elif pos.get("earnings_date_within_dte") is None:
        flags.append("earnings date unknown → event risk unassessed")
    if k == "call" and pos.get("ex_dividend_within_dte") and pos.get("dividend") and out["now"]["extrinsic_left"] < float(pos["dividend"]):
        flags.append("ex-dividend inside DTE and extrinsic < dividend → early assignment likely")
    out["flags"] = flags
    hints = []
    lo, hi = HEURISTICS["take_profit_captured"]
    if captured is not None and captured >= lo:
        hints.append(f"已赚 {captured:.0%} 权利金：剩余最多 {out['now']['extrinsic_left']:.2f}/股，承担的仍是整份指派与跳空风险——"
                     f"常见做法是在 {lo:.0%}–{hi:.0%} 区间考虑买回 (heuristic_unverified)")
    if dte <= HEURISTICS["gamma_zone_dte"] and model["p_itm"] > 0.3:
        hints.append("临近到期且被指派概率（模型）>30%：若不愿被指派，应提前决定买回或展期 (heuristic_unverified)")
    out["shadow_hints"] = hints or ["无触发的管理提示；继续观察 (heuristic_unverified)"]
    out["status"] = "modelled"
    return out


if __name__ == "__main__":
    import json
    demo = {"kind": "put", "strike": 900, "premium_received": 30.0, "mark": None, "underlying": 995.41, "dte": 12, "iv": 0.75,
            "earnings_date_within_dte": None}
    print(json.dumps(compare(demo), ensure_ascii=False, indent=1))
