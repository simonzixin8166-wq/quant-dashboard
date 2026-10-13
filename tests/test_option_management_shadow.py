"""OPT-01: option management Shadow — no orders, IV required, real roll quotes only, heuristics labelled."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import option_management_shadow as om  # noqa: E402

base = {"kind": "put", "strike": 900, "premium_received": 30.0, "underlying": 995.41, "dte": 12, "iv": 0.75, "earnings_date_within_dte": False}
r = om.compare(base)
assert r["production_use"] is False and r["used_in_decision"] is False and r["automatic_orders"] is False
assert r["status"] == "modelled" and r["mark_source"] == "model_estimate_no_quote"
assert set(r["paths"]) == {"close_now", "hold_to_expiry", "assigned", "roll"} and r["paths"]["roll"]["status"] == "quote_required"
assert "not win rates" in r["assumptions"]["model"]
assert r["stress"]["gap_down_10pct"]["p_itm_model"] > r["now"]["p_itm_at_expiry_model"] > r["stress"]["gap_up_10pct"]["p_itm_model"]
assert all("heuristic_unverified" in h for h in r["shadow_hints"])
# no IV → incomplete; realised vol shown only as illustration
r2 = om.compare({**base, "iv": None, "rv": 0.72})
assert r2["status"] == "model_inputs_incomplete" and "implied_volatility" in r2["missing"] and "illustrative_rv_not_iv" in r2 and "paths" not in r2
# quote vs model divergence is flagged
r3 = om.compare({**base, "strike": 960, "mark": 8.0})
assert any("divergence" in f for f in r3["flags"])
# take-profit heuristic appears once most premium is captured
mark = om._bs(995.41, 900, 12, 0.75, "put")["price"]
r4 = om.compare({**base, "premium_received": mark / 0.3, "mark": mark})
assert r4["now"]["premium_captured_pct"] >= 0.5 and any("考虑买回" in h for h in r4["shadow_hints"])
# real roll quote → net credit computed
r5 = om.compare({**base, "roll_quote": {"strike": 880, "dte": 40, "premium": mark + 5}})
assert r5["paths"]["roll"]["net_credit_per_share"] > 0
# covered call: assigned path = shares called away; early assignment flag around ex-dividend; uncovered warned
cc = {"kind": "call", "strike": 36, "premium_received": 1.2, "underlying": 34.8, "dte": 5, "iv": 0.9, "shares_held": 100,
      "ex_dividend_within_dte": True, "dividend": 5.0, "earnings_date_within_dte": None}
r6 = om.compare(cc)
assert r6["covered"] and "shares_delivered" in r6["paths"]["assigned"] and any("early assignment" in f for f in r6["flags"])
assert any("earnings date unknown" in f for f in r6["flags"])
assert "warning" in om.compare({**cc, "shares_held": 0})
# DTE stages
assert om.dte_stage(2).startswith("1-3") and om.dte_stage(7).startswith("4-10") and om.dte_stage(20).startswith("11-30")
# private positions never stored by this module (pure function, no file writes)
src = (Path(__file__).resolve().parents[1] / "scripts" / "option_management_shadow.py").read_text(encoding="utf-8")
assert "write_text" not in src and "open(" not in src
print("PASS option management shadow")
