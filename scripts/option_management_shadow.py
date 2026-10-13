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
  - private positions never enter the public repo: callers pass a position dict at runtime;
  - fees and slippage use one cost convention on every path and stress case (#133 6148675138);
  - a real bid/ask is required for executable P&L and rolls; theoretical prices stay labelled as theory;
  - contracts, multiplier and an anonymous account_id are explicit; covered calls count only shares in the same account.
production_use=false, used_in_decision=false, automatic_orders=false.
"""
from __future__ import annotations
import hashlib, math, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_option_math import calc_option_greeks, norm_cdf  # noqa: E402

CONTRACT = 100  # default multiplier for standard US equity options; always passed through explicitly
HEURISTICS = {"take_profit_captured": (0.50, 0.80), "gamma_zone_dte": 7}
MODEL_QUOTE_DIVERGENCE = 0.25
ANON_ACCOUNT = re.compile(r"^acct_[a-z0-9]{4,16}$")


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


def anonymous_account_id(raw, salt):
    """Runtime-only mapping of a private broker account id to a stable anonymous id (never stored publicly)."""
    if not salt:
        raise ValueError("salt required: an unsalted hash of a short account id is guessable")
    return "acct_" + hashlib.sha256(f"{salt}:{raw}".encode()).hexdigest()[:10]


def _quote(pos):
    """Executable quote for the held contract: {'bid','ask','ts'}; legacy 'mark' is accepted as the ask
    (timestamp unknown). Returns (quote|None, flags)."""
    q = dict(pos.get("quote") or {})
    flags = []
    if not q and pos.get("mark") is not None:
        q = {"ask": float(pos["mark"]), "bid": None, "ts": None, "legacy_mark": True}
    if not q or q.get("ask") in (None, 0):
        return None, flags
    if not q.get("ts"):
        flags.append("quote timestamp unknown → freshness unverified")
    if q.get("bid") is not None and q["ask"] > 0 and (q["ask"] - q["bid"]) / q["ask"] > 0.20:
        flags.append(f"wide bid/ask spread {q['bid']:.2f}/{q['ask']:.2f} → fills uncertain")
    return q, flags


def compare(pos, fees_per_contract=0.65, slippage=0.02, assignment_fee=0.0):
    """pos: kind put|call, strike, premium_received (per share), underlying, dte, iv (decimal, optional),
    contracts (default 1), multiplier (default 100), account_id (anonymous 'acct_…', optional),
    quote {bid, ask, ts} for the held contract (optional; legacy 'mark' = ask), rv (optional),
    shares_held_same_account (covered calls; legacy 'shares_held'), earnings_date_within_dte, ex_dividend_within_dte,
    dividend, roll_quote {strike, dte, bid, ask, ts} (optional; legacy 'premium' = bid).

    Cost convention (identical on every path): buying to close pays (ask + slippage) × multiplier × contracts
    + fees × contracts; selling to open receives (bid − slippage) × multiplier × contracts − fees × contracts;
    expiry worthless costs nothing; assignment costs assignment_fee × contracts.
    Theoretical (Black–Scholes) prices are never presented as an executable fill price."""
    k, K, S, dte = pos["kind"], float(pos["strike"]), float(pos["underlying"]), int(pos["dte"])
    prem = float(pos["premium_received"])
    n = int(pos.get("contracts") or 1)
    mult = int(pos.get("multiplier") or CONTRACT)
    acct = pos.get("account_id")
    shares = pos.get("shares_held_same_account", pos.get("shares_held"))
    out = {"production_use": False, "used_in_decision": False, "automatic_orders": False,
           "kind": k, "contracts": n, "multiplier": mult, "account_id": acct, "dte_stage": dte_stage(dte),
           "assumptions": {"model": "Black-Scholes, r=4%, European approximation; probabilities are risk-neutral estimates, not win rates",
                           "fees_per_contract": fees_per_contract, "slippage_per_share": slippage, "assignment_fee_per_contract": assignment_fee,
                           "cost_convention": "buy-to-close at ask+slippage, sell-to-open at bid−slippage, fees per contract on every traded leg"}}
    if acct is not None and not ANON_ACCOUNT.match(str(acct)):
        out["status"] = "account_id_not_anonymous"
        out["note"] = "pass anonymous_account_id(raw, salt); a raw broker account id is never accepted"
        out.pop("account_id")
        return out
    if k == "call":
        if shares is None:
            out["covered"] = None
            out["coverage_status"] = "private_data_unavailable"
        else:
            out["covered"] = int(shares) >= n * mult
            out["coverage_status"] = "covered_same_account" if out["covered"] else "uncovered_or_partial"
            if not out["covered"]:
                out["warning"] = (f"uncovered call: {int(shares)} shares in this account < {n} × {mult} — unlimited upside risk, "
                                  "outside the owner's covered-call scope (other accounts never offset)")
    else:
        out["covered"] = None
    iv = pos.get("iv")
    q, qflags = _quote(pos)
    if iv is None:
        out["status"] = "model_inputs_incomplete"
        out["missing"] = ["implied_volatility"] + ([] if q else ["option_quote"])
        if pos.get("rv"):
            out["illustrative_rv_not_iv"] = _bs(S, K, dte, float(pos["rv"]), k)
        return out
    model = _bs(S, K, dte, float(iv), k)
    sh = mult * n

    def close_cost(ask):
        return (ask + slippage) * sh + fees_per_contract * n

    intrinsic = max(0.0, (S - K) if k == "call" else (K - S))
    flags = list(qflags)
    out["model"] = {"theoretical_price": round(model["price"], 4), "delta": None if model["delta"] is None else round(model["delta"], 4),
                    "p_itm_at_expiry_model": round(model["p_itm"], 4), "basis": "theoretical — not an executable price"}
    divergence = None
    if q:
        divergence = abs(model["price"] - q["ask"]) / max(q["ask"], model["price"]) if max(q["ask"], model["price"]) > 0 else 0.0
        if divergence > MODEL_QUOTE_DIVERGENCE:
            flags.append(f"model/quote divergence: model {model['price']:.2f} vs ask {q['ask']:.2f} — the IV input does not match the market; "
                         "stress figures unreliable (model_uncertainty)")
    ref = q["ask"] if q else model["price"]
    captured = (prem - ref) / prem if prem > 0 else None
    out["mark_source"] = "quote_ask" if q else "model_estimate_no_quote"
    out["quote"] = ({"bid": q.get("bid"), "ask": q["ask"], "ts": q.get("ts")} if q else None)
    out["now"] = {"premium_captured_pct": None if captured is None else round(captured, 4), "reference_price": round(ref, 4),
                  "reference_basis": "executable ask" if q else "theoretical (no quote) — not executable",
                  "intrinsic": round(intrinsic, 4), "extrinsic_left": round(max(0.0, ref - intrinsic), 4),
                  "delta": out["model"]["delta"], "p_itm_at_expiry_model": out["model"]["p_itm_at_expiry_model"]}
    if q:
        close_now = {"status": "quote_based", "pnl_usd": round(prem * sh - close_cost(q["ask"]), 2),
                     "frees_capital_usd": K * sh if k == "put" else 0, "residual_risk": "none after the buy-back fills"}
    else:
        close_now = {"status": "quote_required", "pnl_usd": None,
                     "model_reference_pnl_usd": round(prem * sh - close_cost(model["price"]), 2),
                     "note": "no real bid/ask — theoretical price is not an expected fill"}
    out["paths"] = {
        "close_now": close_now,
        "hold_to_expiry": {"pnl_if_expires_worthless_usd": round(prem * sh, 2),
                           "max_additional_gain_vs_close_usd": None if not q else round(close_cost(q["ask"]), 2),
                           "p_assignment_model": out["model"]["p_itm_at_expiry_model"],
                           "residual_risk": "gap through the strike; assignment" + (" (early assignment risk around ex-dividend)" if k == "call" else "")},
        "assigned": ({"cash_needed_usd": K * sh, "effective_cost_basis": round(K - prem - assignment_fee / mult, 4),
                      "mark_to_market_vs_basis_usd": round((S - (K - prem)) * sh - assignment_fee * n, 2)} if k == "put" else
                     {"shares_delivered": sh, "effective_sale_price": round(K + prem - assignment_fee / mult, 4),
                      "opportunity_cost_if_above_strike_usd": round(max(0.0, S - K) * sh, 2)}),
    }
    rq = pos.get("roll_quote")
    rbid = None if not rq else (rq.get("bid") if rq.get("bid") is not None else rq.get("premium"))
    if rq and rbid is not None and q:
        net = (float(rbid) - slippage) - (q["ask"] + slippage)
        out["paths"]["roll"] = {"status": "quote_based", "to": {k2: rq.get(k2) for k2 in ("strike", "dte", "bid", "ask", "ts")},
                                "net_credit_per_share": round(net, 4), "net_credit_usd": round(net * sh - 2 * fees_per_contract * n, 2),
                                "note": "roll only with real quotes for both legs; a net debit is a cost, not a fix"}
    else:
        out["paths"]["roll"] = {"status": "quote_required",
                                "note": "needs a real bid for the new contract and a real ask for the held contract — not modelled"}
    stress = {}
    for name, dS, dIV in (("gap_down_5pct", -0.05, 0), ("gap_down_10pct", -0.10, 0), ("gap_up_10pct", 0.10, 0), ("iv_plus_10pts", 0, 0.10)):
        m = _bs(S * (1 + dS), K, dte, float(iv) + dIV, k)
        stress[name] = {"option_value_model": round(m["price"], 4), "pnl_if_closed_usd": round(prem * sh - close_cost(m["price"]), 2),
                        "p_itm_model": round(m["p_itm"], 4), "basis": "theoretical price + same slippage/fees as close_now"}
    out["stress"] = stress
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
                     f"常见做法是在 {lo:.0%}–{hi:.0%} 区间考虑买回 (heuristic_unverified)" + ("" if q else "；无真实报价，比例为理论估计"))
    if dte <= HEURISTICS["gamma_zone_dte"] and model["p_itm"] > 0.3:
        hints.append("临近到期且被指派概率（模型）>30%：若不愿被指派，应提前决定买回或展期 (heuristic_unverified)")
    out["shadow_hints"] = hints or ["无触发的管理提示；继续观察 (heuristic_unverified)"]
    out["status"] = ("quote_required" if not q else "model_uncertainty" if divergence is not None and divergence > MODEL_QUOTE_DIVERGENCE else "modelled")
    return out


def account_view(account_id, short_options, shares_by_symbol, **kw):
    """All short options of ONE account. Covered-call coverage is computed per symbol inside this account only:
    shares_by_symbol=None → private_data_unavailable (never borrowed from another account)."""
    if not ANON_ACCOUNT.match(str(account_id)):
        return {"status": "account_id_not_anonymous"}
    rows = []
    used = {}
    for o in sorted(short_options, key=lambda o: (o["kind"] != "call", o.get("dte", 0))):
        o = {**o, "account_id": account_id}
        if o["kind"] == "call":
            if shares_by_symbol is None:
                o["shares_held_same_account"] = None
            else:
                free = int(shares_by_symbol.get(o["symbol"], 0)) - used.get(o["symbol"], 0)
                o["shares_held_same_account"] = max(0, free)
                used[o["symbol"]] = used.get(o["symbol"], 0) + int(o.get("contracts") or 1) * int(o.get("multiplier") or CONTRACT)
        rows.append({"symbol": o["symbol"], **compare(o, **kw)})
    return {"account_id": account_id, "positions": rows, "production_use": False,
            "coverage_basis": "same account only; shares in other accounts never offset a covered call",
            "private_data": "unavailable" if shares_by_symbol is None else "runtime_only_not_stored"}


def from_private_rows(option_rows, stock_rows, salt):
    """Adapter for the existing private read path (Supabase options_positions / stock_positions, owner-only RLS),
    used at runtime inside the private server job only. Raw broker_account_id never leaves this function."""
    accounts = {}
    for r in option_rows or []:
        a = anonymous_account_id(r["broker_account_id"], salt)
        accounts.setdefault(a, {"options": [], "shares": None})["options"].append(
            {"symbol": r["symbol"], "kind": r["kind"], "strike": r["strike"], "contracts": abs(int(r["qty"])),
             "multiplier": int(r.get("multiplier") or CONTRACT), "premium_received": r["premium_per_share"],
             "dte": r["dte"], "underlying": r.get("underlying"), "iv": r.get("iv"), "quote": r.get("quote")})
    if stock_rows is not None:
        for r in stock_rows:
            a = anonymous_account_id(r["broker_account_id"], salt)
            acc = accounts.setdefault(a, {"options": [], "shares": None})
            acc["shares"] = acc["shares"] or {}
            acc["shares"][r["symbol"]] = acc["shares"].get(r["symbol"], 0) + int(r["shares"])
        for acc in accounts.values():
            if acc["shares"] is None:
                acc["shares"] = {}
    return accounts


if __name__ == "__main__":
    import json
    demo = {"kind": "put", "strike": 900, "premium_received": 30.0, "mark": None, "underlying": 995.41, "dte": 12, "iv": 0.75,
            "earnings_date_within_dte": None}
    print(json.dumps(compare(demo), ensure_ascii=False, indent=1))
