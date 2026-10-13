"""OPT-01: option management Shadow — no orders, IV required, real quotes for executable P&L and rolls,
one cost convention on every path (#133 6148675138), per-account covered-call coverage, heuristics labelled."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import option_management_shadow as om  # noqa: E402

F, SL = 0.65, 0.02
base = {"kind": "put", "strike": 900, "premium_received": 30.0, "underlying": 995.41, "dte": 12, "iv": 0.75, "earnings_date_within_dte": False}
r = om.compare(base)
assert r["production_use"] is False and r["used_in_decision"] is False and r["automatic_orders"] is False
# no quote: theoretical price is never an executable fill → quote_required, P&L only as a labelled model reference
assert r["status"] == "quote_required" and r["mark_source"] == "model_estimate_no_quote"
assert r["paths"]["close_now"]["status"] == "quote_required" and r["paths"]["close_now"]["pnl_usd"] is None
assert "not executable" in r["now"]["reference_basis"] and "not an executable" in r["model"]["basis"]
assert set(r["paths"]) == {"close_now", "hold_to_expiry", "assigned", "roll"} and r["paths"]["roll"]["status"] == "quote_required"
assert "not win rates" in r["assumptions"]["model"]
assert r["stress"]["gap_down_10pct"]["p_itm_model"] > r["now"]["p_itm_at_expiry_model"] > r["stress"]["gap_up_10pct"]["p_itm_model"]
assert all("heuristic_unverified" in h for h in r["shadow_hints"])

# ---- fix 1: identical cost convention on close_now and every stress case (regression: stress ignored costs)
q = {"bid": 16.2, "ask": 16.6, "ts": "2026-10-13T19:55:00Z"}
rq = om.compare({**base, "quote": q})
assert rq["status"] == "modelled" and rq["mark_source"] == "quote_ask"
assert rq["paths"]["close_now"]["pnl_usd"] == round(30.0 * 100 - ((16.6 + SL) * 100 + F), 2) == 1337.35
for name, st in rq["stress"].items():
    assert st["pnl_if_closed_usd"] == round(30.0 * 100 - ((st["option_value_model"] + SL) * 100 + F), 2), name
# a stress case with zero move and zero IV change equals close_now priced at the model value (same convention)
same = om.compare({**base, "quote": {"bid": None, "ask": om._bs(995.41, 900, 12, 0.75, "put")["price"], "ts": "x"}})
m = same["model"]["theoretical_price"]
assert abs(same["paths"]["close_now"]["pnl_usd"] - round(3000 - ((m + SL) * 100 + F), 2)) < 0.02
assert rq["paths"]["hold_to_expiry"]["pnl_if_expires_worthless_usd"] == 3000.0
assert rq["paths"]["hold_to_expiry"]["max_additional_gain_vs_close_usd"] == round((16.6 + SL) * 100 + F, 2)
# contracts and multiplier scale every path and the fees per contract
r3c = om.compare({**base, "quote": q, "contracts": 3})
assert r3c["paths"]["close_now"]["pnl_usd"] == round(30.0 * 300 - ((16.6 + SL) * 300 + 3 * F), 2)
assert r3c["paths"]["assigned"]["cash_needed_usd"] == 900 * 300
assert r3c["stress"]["gap_down_5pct"]["pnl_if_closed_usd"] == round(9000 - ((r3c["stress"]["gap_down_5pct"]["option_value_model"] + SL) * 300 + 3 * F), 2)
mini = om.compare({**base, "quote": q, "multiplier": 10})
assert mini["paths"]["close_now"]["pnl_usd"] == round(300 - ((16.6 + SL) * 10 + F), 2) and mini["multiplier"] == 10

# ---- fix 2: model/quote divergence → model_uncertainty, legacy mark = ask with unknown timestamp
r3 = om.compare({**base, "strike": 960, "mark": 8.0})
assert r3["status"] == "model_uncertainty" and any("divergence" in f for f in r3["flags"])
assert any("timestamp unknown" in f for f in r3["flags"])
assert any("wide bid/ask" in f for f in om.compare({**base, "quote": {"bid": 10.0, "ask": 16.6, "ts": "t"}})["flags"])
# roll needs real quotes for BOTH legs; net credit uses bid−slippage / ask+slippage and two legs of fees
assert om.compare({**base, "roll_quote": {"strike": 880, "dte": 40, "bid": 25.0}})["paths"]["roll"]["status"] == "quote_required"
r5 = om.compare({**base, "quote": q, "roll_quote": {"strike": 880, "dte": 40, "bid": 21.0, "ask": 21.6, "ts": "t"}})
assert r5["paths"]["roll"]["net_credit_per_share"] == round((21.0 - SL) - (16.6 + SL), 4)
assert r5["paths"]["roll"]["net_credit_usd"] == round(((21.0 - SL) - (16.6 + SL)) * 100 - 2 * F, 2)

# no IV → incomplete; realised vol shown only as illustration
r2 = om.compare({**base, "iv": None, "rv": 0.72})
assert r2["status"] == "model_inputs_incomplete" and "implied_volatility" in r2["missing"] and "option_quote" in r2["missing"]
assert "illustrative_rv_not_iv" in r2 and "paths" not in r2
# take-profit heuristic appears once most premium is captured (quote-based)
mark = om._bs(995.41, 900, 12, 0.75, "put")["price"]
r4 = om.compare({**base, "premium_received": mark / 0.3, "quote": {"bid": mark - 0.1, "ask": mark, "ts": "t"}})
assert r4["now"]["premium_captured_pct"] >= 0.5 and any("考虑买回" in h for h in r4["shadow_hints"])

# ---- fix 3/4: covered calls count only shares in the SAME account; missing private data is explicit
cc = {"symbol": "IREN", "kind": "call", "strike": 36, "premium_received": 1.2, "underlying": 34.8, "dte": 5, "iv": 0.9,
      "ex_dividend_within_dte": True, "dividend": 5.0, "earnings_date_within_dte": None}
r6 = om.compare({**cc, "shares_held_same_account": 100})
assert r6["covered"] and r6["coverage_status"] == "covered_same_account" and "shares_delivered" in r6["paths"]["assigned"]
assert any("early assignment" in f for f in r6["flags"]) and any("earnings date unknown" in f for f in r6["flags"])
assert "warning" in om.compare({**cc, "shares_held": 0})                            # legacy key still honoured
assert om.compare({**cc, "contracts": 2, "shares_held_same_account": 150})["coverage_status"] == "uncovered_or_partial"
assert om.compare(cc)["coverage_status"] == "private_data_unavailable" and om.compare(cc)["covered"] is None
A, B = om.anonymous_account_id("1001", "s"), om.anonymous_account_id("2002", "s")
assert A != B and A.startswith("acct_") and om.anonymous_account_id("1001", "s") == A
try:
    om.anonymous_account_id("1001", "")
    raise SystemExit("unsalted ids must be refused")
except ValueError:
    pass
assert om.compare({**cc, "account_id": "1234567890"})["status"] == "account_id_not_anonymous"
# IREN: account A holds 100 shares and 2 short calls; account B holds 300 shares and no calls → A stays partially uncovered
va = om.account_view(A, [{**cc, "contracts": 1}, {**cc, "strike": 38, "contracts": 1}], {"IREN": 100})
assert [p["coverage_status"] for p in va["positions"]] == ["covered_same_account", "uncovered_or_partial"]
assert "never offset" in va["coverage_basis"]
assert all(p["coverage_status"] == "private_data_unavailable" for p in om.account_view(A, [cc], None)["positions"])
# adapter for the existing private read path: raw broker ids never appear in the output
acc = om.from_private_rows([{"broker_account_id": 1001, "symbol": "IREN", "kind": "call", "strike": 36, "qty": -2, "premium_per_share": 1.2, "dte": 5},
                            {"broker_account_id": 2002, "symbol": "IREN", "kind": "put", "strike": 30, "qty": -1, "premium_per_share": 1.0, "dte": 5}],
                           [{"broker_account_id": 2002, "symbol": "IREN", "shares": 300}], salt="s")
assert set(acc) == {A, B} and acc[A]["shares"] == {} and acc[B]["shares"] == {"IREN": 300} and acc[A]["options"][0]["contracts"] == 2
assert "1001" not in json.dumps(acc) and "2002" not in json.dumps(acc)
assert om.from_private_rows([{"broker_account_id": 1001, "symbol": "IREN", "kind": "call", "strike": 36, "qty": -1, "premium_per_share": 1.2, "dte": 5}],
                            None, salt="s")[A]["shares"] is None              # stock rows unavailable ≠ zero shares

# DTE stages
assert om.dte_stage(2).startswith("1-3") and om.dte_stage(7).startswith("4-10") and om.dte_stage(20).startswith("11-30")
# private positions never stored by this module (pure functions, no file writes)
src = (Path(__file__).resolve().parents[1] / "scripts" / "option_management_shadow.py").read_text(encoding="utf-8")
assert "write_text" not in src and "open(" not in src
print("PASS option management shadow")
