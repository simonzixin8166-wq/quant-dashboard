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
