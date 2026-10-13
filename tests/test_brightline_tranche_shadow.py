"""R-B (#133 6138763764): BrightLine three-tranche Shadow state machine — fail-closed, AND/OR fidelity,
a date never triggers, author thresholds stay author's, allocation never inferred, never used in decisions."""
import copy, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import brightline_tranche_shadow as bl  # noqa: E402

EXP = "2026-10-12"
BASE = {"expected_session": EXP,
        "macro": {"y10": {"value": 5.22, "date": "2026-10-08", "change_20": 0.27, "max_10": None}},
        "breadth": {"b200": 0.519, "as_of": "2026-10-12", "new_low_52w_pct": 0.016, "new_low_trend": None, "coverage": 499, "universe": 503},
        "events": {"events": {}},
        "core": {"QQQM": {"drawdown": -0.022, "date": "2026-10-12", "tiers": {"t1": 0.12}},
                 "VGT": {"drawdown": -0.032, "date": "2026-10-12", "tiers": {"t1": 0.15}}}}


def ev(**kw):
    return {"official_outcome_recorded_at": "2026-10-14T13:00:00Z", **kw}


def run(mut=None):
    x = copy.deepcopy(BASE)
    if mut:
        mut(x)
    return bl.evaluate(x)


s = run()
assert s["used_in_decision"] is False and s["production_use"] is False and s["automatic_orders"] is False
assert s["allocation"]["status"] == "allocation_unset" and "never inferred" in s["allocation"]["tranche_sizes"]
assert "NOT applied" in s["allocation"]["author_cash_floor"]
assert s["overall"] == "neutral_awaiting_confirmation" and s["overall_zh"] == "中性待确认"
t1, t2, t3 = (s["tranches"][k] for k in ("1_policy_rate", "2_breadth_confirmation", "3_price_levels"))
assert t1["state"] == "not_met"            # 10Y 5.22 not < 5, trend not down; refunding unknown
assert t2["state"] == "unknown"            # main branch unmet (10Y ≥ 5) but December FOMC branch unknown → OR stays unknown
assert t3["state"] == "not_met"            # existing tiers not reached
assert all(c.get("threshold_kind") == "author_threshold" for c in t1["early"] if c["name"].startswith("y10_below"))
assert "connective_source" in t1 and "full text verified" in t1["connective_source"]

# A date arriving never satisfies a condition: the 11/04 refunding stays unknown until an official outcome is recorded
s2 = run(lambda x: x.update(expected_session="2026-11-05"))
ref = [c for c in s2["tranches"]["1_policy_rate"]["main"] if c["name"].startswith("refunding")][0]
assert ref["status"] == "unknown"

# OR fidelity: soft CPI AND 10Y < 5 % → tranche 1 candidate even though the refunding branch is unknown
def soft(x):
    x["events"]["events"]["cpi_2026_09"] = ev(surprise="soft", summary="core 0.1% m/m")
    x["macro"]["y10"].update(value=4.95, change_20=-0.3)
s3 = run(soft)
assert s3["tranches"]["1_policy_rate"]["state"] == "candidate" and s3["overall"] == "conditions_improving"
# AND fidelity: soft CPI alone (10Y still ≥ 5 %) is not enough
s3b = run(lambda x: x["events"]["events"].update(cpi_2026_09=ev(surprise="soft")))
assert s3b["tranches"]["1_policy_rate"]["state"] == "not_met"

# risk_off freezes tranches 1–2 but not tranche 3; a met tranche becomes conflict_frozen, never a buy
def hot_but_low_yield(x):
    soft(x)
    x["events"]["events"]["fomc_2026_10"] = ev(hiked=True, summary="surprise hike")
s4 = run(hot_but_low_yield)
assert s4["risk_off"]["active"] and s4["risk_off"]["freezes_tranches"] == [1, 2]
assert s4["tranches"]["1_policy_rate"]["state"] == "conflict_frozen" and s4["overall"] == "risk_elevated"
s5 = run(lambda x: x["macro"]["y10"].update(value=5.40))
assert s5["risk_off"]["active"] and s5["overall"] == "risk_elevated"
def deep_drawdown(x):
    x["core"]["QQQM"]["drawdown"] = -0.13
    x["macro"]["y10"]["value"] = 5.40
s6 = run(deep_drawdown)
assert s6["tranches"]["3_price_levels"]["state"] == "price_condition_met_needs_manual_budget_and_guardrail_check"

# fail-closed: stale or missing data → unknown / data_insufficient, never an optimistic carry-over
s7 = run(lambda x: x["macro"]["y10"].update(date="2026-09-25"))
assert s7["overall"] == "data_insufficient" and s7["risk_off"]["data_stale"]
assert all(c["status"] == "unknown" for c in s7["tranches"]["1_policy_rate"]["early"] if c["name"].startswith("y10"))
s8 = run(lambda x: x["breadth"].update(b200=None))
assert s8["overall"] == "data_insufficient"
assert [c for c in s8["tranches"]["2_breadth_confirmation"]["main"] if c["name"].startswith("spx")][0]["status"] == "unknown"
s9 = run(lambda x: x["core"]["QQQM"].update(date="2026-09-01"))
assert [c for c in s9["tranches"]["3_price_levels"]["conditions"] if c["name"].startswith("QQQM")][0]["status"] == "unknown"
# breadth is never replaced by an index proxy
b = [c for c in s["tranches"]["2_breadth_confirmation"]["main"] if c["name"].startswith("spx")][0]
assert "never IWM/SPY proxy" in b["note"]

# idempotent and pure: same inputs → same result; inputs untouched
x = copy.deepcopy(BASE)
assert bl.evaluate(x) == bl.evaluate(x) and x == BASE

# the committed state file is inert
st = json.loads((ROOT / "research" / "macro_events" / "brightline_three_tranche_state.json").read_text(encoding="utf-8"))
assert st["used_in_decision"] is False and st["production_use"] is False and st["rules_version"] == bl.RULES_VERSION
# event calendar: official outcomes are empty until recorded; times carry ET and Beijing labels
cal = json.loads((ROOT / "research" / "macro_events" / "event_facts_2026q4.json").read_text(encoding="utf-8"))
for k, e in cal["events"].items():
    assert e["release"]["et"] and e["release"]["beijing"] and e["checkpoints"]["T+10"], k
assert cal["events"]["cpi_2026_09"]["release"]["beijing_label"].startswith("10/14 20:30")
assert cal["events"]["treasury_refunding_2026_11_04"]["release"]["et_label"].endswith("EST")  # after DST ends 11/01
print("PASS BrightLine three-tranche shadow")


# Full-text verification record (6142705659): hash matches owner's, no full text stored, short excerpts only
V = json.loads((ROOT / "research" / "audit" / "brightline_8524_fulltext_verification_v0_3.json").read_text(encoding="utf-8"))
assert V["source"]["matches_owner_hash"] is True and V["source"]["normalized_text_sha256"].startswith("f909e1b9")
assert V["source"]["paragraphs"] == 50 == len(V["paragraph_locators"]) and V["source"]["chars"] == 3266
assert all(set(p) == {"loc", "section", "is_heading", "chars", "sha256_16"} for p in V["paragraph_locators"])
assert sum(len(x) for x in V["connective_excerpts"]["items"].values()) <= 360
assert all(c["verdict"].startswith("match") for c in V["connective_verification"])
assert V["used_in_decision"] is False and V["production_use"] is False
print("full-text verification record OK")
