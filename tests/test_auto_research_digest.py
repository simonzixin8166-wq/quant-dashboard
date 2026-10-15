"""#133 6109957428 P0-3: homepage digest counts are real, per distinct symbol, exclude same-session generator
upgrades, flag pre-SEC-gate evidence, and carry no private fields."""
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import auto_research_digest as ard  # noqa: E402


def h(sym, day, gen, stance="neutral", fund=False):
    ev = [{"name": "close_vs_ma50", "group": "trend", "note": "close above MA50", "source": "stooq archive", "as_of": day}]
    if fund:
        ev.append({"name": "sec_revenue_yoy", "group": "fundamental", "note": "revenue +10%", "source": "SEC XBRL", "as_of": day})
    return {"type": "hypothesis", "symbol": sym, "market_as_of": day, "generator_version": gen, "stance": stance,
            "record_id": f"{sym}-{day}-{gen}-h", "research_date": day, "supporting": ev, "opposing": [],
            "invalidation": [{"metric": "close", "op": "<", "ref": "ma50", "note": "close back below MA50"}],
            "next_review": "2026-11-09", "inputs": {"price_archive": {}, "sec_facts": {}}}


def rv(sym, day, gen, status, hid, upgrade=False):
    r = {"type": "revisit", "symbol": sym, "market_as_of": day, "generator_version": gen, "status": status,
         "hypothesis_id": hid, "record_id": f"{sym}-{day}-{gen}-{'supersede' if upgrade else 'revisit'}"}
    r["trigger"] = {"reason": "generator upgrade auto-research-3 → auto-research-4"} if upgrade else ({"note": "close back below MA50"} if status == "invalidated" else None)
    return r


D1, D2 = "2026-10-09", "2026-10-12"
J = [h("AAA", D1, "auto-research-3", fund=True), h("BBB", D1, "auto-research-3"),
     h("AAA", D1, "auto-research-4", fund=True), rv("AAA", D1, "auto-research-4", "superseded", "AAA-2026-10-09-auto-research-3-h", upgrade=True),
     {"type": "abstain", "symbol": "ZZZ", "market_as_of": D1, "decision_reason": "insufficient canonical history"},
     # next session: AAA invalidated + new bearish hypothesis, BBB still valid, ZZZ abstains again
     rv("AAA", D2, "auto-research-4", "invalidated", "AAA-2026-10-09-auto-research-4-h"),
     h("AAA", D2, "auto-research-4", stance="bearish"),
     rv("BBB", D2, "auto-research-4", "still_valid", "BBB-2026-10-09-auto-research-3-h"),
     {"type": "abstain", "symbol": "ZZZ", "market_as_of": D2, "decision_reason": "insufficient canonical history"},
     {"type": "annotation", "annotates": "BBB-2026-10-09-auto-research-3-h", "kind": "sec_correction", "note": "corrected", "generated_at": "x"}]
now = datetime(2026, 10, 13, 2, 0, tzinfo=timezone.utc)
d = ard.build(J, {"last_run_at": "2026-10-13T00:40:00Z", "last_run_id": "1"}, None, now)
assert d["latest_session"] == D2
assert d["counts"]["new"] == 1 and d["new_symbols"] == ["AAA"], d["counts"]
assert d["counts"]["invalidated"] == 1 and d["invalidated"][0]["trigger"] == "close back below MA50"
assert d["counts"]["abstained"] == 1 and d["counts"]["revisited_cross_day"] == 2 and d["counts"]["still_valid"] == 1
assert d["counts"]["active"] == 2
items = {i["symbol"]: i for i in d["items"]}
assert items["AAA"]["stance"] == "bearish" and items["AAA"]["new_this_session"] and not items["AAA"]["pre_sec_gate"]
assert items["BBB"]["pre_sec_gate"] and items["BBB"]["annotations"][0]["kind"] == "sec_correction"
assert items["AAA"]["invalidation"] == ["close back below MA50"] and items["AAA"]["inputs"] == ["price_archive", "sec_facts"]
# first session alone: regenerations count once; engineering supersede is not research
d1 = ard.build(J[:5], {"last_run_at": "x"}, None, now)
assert d1["counts"]["new"] == 2 and d1["counts"]["revisited_cross_day"] == 0 and d1["counts"]["abstained"] == 1
pre = [i for i in d1["items"] if i["symbol"] == "BBB"][0]
assert pre["pre_sec_gate"] and not any(e.get("pre_sec_gate") for e in pre["supporting"]), "only fundamental evidence is flagged"
aaa3 = ard.build(J[:2], {}, None, now)["items"][0]
assert [e for e in aaa3["supporting"] if e["group"] == "fundamental"][0]["pre_sec_gate"] is True
# failure marker after the last success → failed
f = ard.build(J, {"last_run_at": "2026-10-12T00:00:00Z"}, {"modules": {"auto_research": {"failed_at": "2026-10-13T00:00:00Z", "run_id": "9"}}}, now)
assert f["run_failure"]["failed_after_last_success"] is True
ok = ard.build(J, {"last_run_at": "2026-10-14T00:00:00Z"}, {"modules": {"auto_research": {"failed_at": "2026-10-13T00:00:00Z"}}}, now)
assert ok["run_failure"]["failed_after_last_success"] is False
# empty journal
e = ard.build([], None, None, now)
assert e["latest_session"] is None and e["counts"]["new"] == 0 and e["status_available"] is False
# shadow labels and no private fields
assert d["production_use"] is False and d["forward_eligible"] is False and d["learning_state"] == "UNPROVEN"
blob = str(d).lower()
for bad in ("shares", "quantity", "broker", "account", "cost_basis", "position_size"):
    assert bad not in blob, bad
print("test_auto_research_digest OK")

# B1/B2 experience_basis (#133 6185390674): built only from the record, informational only, never changes research output
import copy, json as _json  # noqa: E402
rel = lambda n: {"status": "descriptive_pooled_only" if n < 30 else "symbol_and_pooled", "min_n": 30, "yoy_bucket": "> +10%",
                 "symbol": {"20": {"n": n}, "60": {"n": n}}, "pooled": {"20": {"n": 135, "positive_rate": 0.54}, "60": {"n": 131}},
                 "used_in_decision": False}
b1 = h("CCC", D2, "auto-research-6", stance="bullish", fund=True)
b1["supporting"][1]["historical_reliability"] = rel(3)
b1.update({"experience_input_status": "used", "record_sha256": "f" * 64,
           "precedents": [{"case_id": "XLK:2026-06-18:s", "date": "2026-06-18", "stage": "s", "return_60": 0.04, "supports_or_conflicts": "supports"},
                          {"case_id": "SMH:2026-06-12:s", "date": "2026-06-12", "stage": "s", "return_60": -0.02, "supports_or_conflicts": "conflicts"}],
           "error_attribution": {"symbol_cases": [{"case_id": "CCC:2026-08-01:x", "tags": ["trend_false_positive"]}], "base_rates": {"scope": "all"}},
           "experience": {"memory_inputs": {"learning": {"as_of": D2, "sha256": "a" * 64, "source": "docs/research/learning_engine.json"}},
                          "excluded": [{"why_excluded": "look-ahead"}]}})
b2 = h("DDD", D2, "auto-research-6", fund=True)
b2["supporting"][1]["historical_reliability"] = rel(40)
b2.update({"experience_input_status": "none", "precedents": [], "error_attribution": {"symbol_cases": []}})
J2 = J + [b1, b2]
d2 = ard.build(J2, {}, None, now)
it = {i["symbol"]: i for i in d2["items"]}
e = it["CCC"]["experience_basis"]
assert e["contract"] == "experience-basis-1" and e["evidence_id"] == b1["record_id"] and e["session"] == D2 and e["record_sha256"] == "f" * 12
assert e["informational_only"] and e["used_in_decision"] is False and e["shadow"] and e["status"] == "used"
assert e["precedents"]["n"] == 2 and e["precedents"]["supports"] == 1 and e["precedents"]["conflicts"] == 1 and abs(e["precedents"]["median_return_60"] - 0.01) < 1e-12
assert e["error_attribution"]["symbol_cases_n"] == 1 and e["error_attribution"]["tags"] == {"trend_false_positive": 1}
assert e["historical_reliability"][0]["strength"] == "descriptive" and e["historical_reliability"][0]["symbol_n_20"] == 3   # n < 30 stays descriptive
assert e["memory_inputs"]["learning"]["sha256"] == "a" * 12 and e["excluded_n"] == 1
assert it["DDD"]["experience_basis"]["status"] == "none" and it["DDD"]["experience_basis"]["historical_reliability"][0]["strength"] == "eligible_for_review"
pre = it["AAA"]["experience_basis"]                        # auto-research-4 record: no B1 fields → unavailable, never a default
assert pre["status"] == "unavailable" and pre["precedents"] == {"status": "unavailable"} and pre["historical_reliability"]["status"] == "unavailable"
cov = d2["experience_coverage"]
assert cov["active_items"] == 4 and cov["used"] == 1 and cov["none"] == 1 and cov["unavailable_or_unknown"] == 2
assert cov["precedent_items"] == 2 and cov["with_historical_reliability"] == 2 and cov["reliability_symbol_n_ge_min"] == 1 and cov["used_in_decision"] == 0
# research output unchanged: stripping every B1/B2 field gives the same items (minus experience_basis) and counts
stripped = copy.deepcopy(J2)
for r in stripped:
    for k in ("experience_input_status", "precedents", "error_attribution", "experience"):
        r.pop(k, None)
    for ev in (r.get("supporting") or []) + (r.get("opposing") or []):
        ev.pop("historical_reliability", None)
d3 = ard.build(stripped, {}, None, now)
drop = lambda d: [{k: v for k, v in i.items() if k != "experience_basis"} for i in d["items"]]
assert drop(d2) == drop(d3) and d2["counts"] == d3["counts"] and d2["new_symbols"] == d3["new_symbols"]
# deterministic / idempotent; a same-session regeneration counts once (latest record per symbol)
assert _json.dumps(ard.build(J2, {}, None, now), sort_keys=True) == _json.dumps(d2, sort_keys=True)
rerun = copy.deepcopy(b1); rerun["record_id"] = "CCC-rerun"
d4 = ard.build(J2 + [rerun], {}, None, now)
assert d4["experience_coverage"]["used"] == 1 and d4["experience_coverage"]["active_items"] == 4
# no cross-record leakage: a later record for another symbol never changes CCC's basis
later = h("EEE", "2026-10-20", "auto-research-6"); later.update({"experience_input_status": "used", "precedents": [{"return_60": 9}]})
assert {i["symbol"]: i for i in ard.build(J2 + [later], {}, None, now)["items"]}["CCC"]["experience_basis"] == e
print("PASS experience_basis contract")
