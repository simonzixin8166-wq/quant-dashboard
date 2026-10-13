"""P3-12 learning funnel contract invariants (on current artifacts + synthetic edge cases)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import learning_funnel_contract as lf

out = lf.build()
assert set(out["engines"]) == {"market", "fundamental", "event", "options", "decision", "external_research"}
for name, f in out["engines"].items():
    for k in lf.LAYERS:
        assert k in f, (name, k)
        L = f[k]
        assert L.get("definition") and L.get("evidence"), (name, k)
        if L["count"] is None:
            assert L.get("reason"), (name, k)  # null must explain itself, never silent
    assert not out["summary"][name]["funnel_issues"], (name, out["summary"][name]["funnel_issues"])
# Historical/descriptive outcomes never flow into the forward layers.
fund = out["engines"]["fundamental"]
assert fund["historical"]["descriptive_outcome_rows"] >= 0
assert fund["effective_forward_eligible"]["count"] is None and fund["independently_matured"]["count"] is None
# Decision learning never invents user actions; private engines expose aggregates only.
txt = json.dumps(out, ensure_ascii=False)
for forbidden in ("broker_account_id", "user_id", "position_id", "gold_budget_usd", "dca_monthly_usd"):
    assert forbidden not in txt, forbidden
# Two tracks: with no genuine forward matured samples the learning track is UNPROVEN.
if out["tracks"]["genuine_forward_matured_total"] == 0:
    assert out["tracks"]["learning_maturity"] == "UNPROVEN"

# Synthetic: outcomes alone are not learning; proven needs matured+benchmark+reuse.
def f(**counts):
    return {k: {"count": counts.get(k)} for k in lf.LAYERS}
assert lf.maturity(f(candidate_claim_or_state=5, independently_matured=10, downstream_consumer_count=9)) == "unproven_no_forward_samples"
assert lf.maturity(f(effective_forward_eligible=3)) == "forward_collecting"
assert lf.maturity(f(effective_forward_eligible=3, independently_matured=2, benchmark_evaluated=2, downstream_consumer_count=5)) == "forward_collecting"  # readers are not applied learning
assert lf.maturity(f(effective_forward_eligible=3, independently_matured=2, benchmark_evaluated=2, validated_learning_applied=1)) == "proven_candidate"
# validated_learning_applied is null (with reason) until provable; consumer counts are readability only.
for name, eng in out["engines"].items():
    assert eng["validated_learning_applied"]["count"] is None and eng["validated_learning_applied"]["reason"], name
    assert "READ" in eng["downstream_consumer_count"]["definition"]
# External research 'interpretable' excludes title-only rows and exposes the text depth split.
ext = out["engines"]["external_research"]["interpretable"]
assert "title-only excluded" in ext["definition"] or ext["count"] is None
assert ext["records_processed_by_source_reading"] >= 0 and "processed ≠ understood" in ext["note"]
assert lf.check("x", f(effective_forward_eligible=1, independently_matured=4)) == ["independently_matured(4) > effective_forward_eligible(1)"]
# Market chain: one maturity floor for both sources (regression for the 2026-10-12 Daily failure,
# where 5-session market-state scorecards (3) exceeded matured macro outcomes (0) once SPY joined).
_m = out["engines"]["market"]
assert lf.MATURE_MIN_SESSIONS == 20
assert "early_reads" in _m and _m["early_reads"]["market_state_outcomes_below_maturity"] >= 0
if _m["benchmark_evaluated"]["count"] and _m["independently_matured"]["count"] is not None:
    assert _m["benchmark_evaluated"]["count"] <= _m["independently_matured"]["count"]
# Event chain (regression for Daily 38340669182: independently_matured(4) > effective_forward_eligible(0)):
# outcomes of backfilled/non-live events or below the maturity floor never count as forward matured.
import tempfile
with tempfile.TemporaryDirectory() as _t:
    _R, _D = Path(_t) / "research", Path(_t) / "docs" / "research"
    (_R / "archive" / "events").mkdir(parents=True); _D.mkdir(parents=True)
    _ev = [{"archive_id": f"e{i}", "uuid": f"e{i}", "title": "t", "url": "u", "event_date": "2026-09-01",
            "used_in_decision": True, "published_at": "2026-09-01T00:00:00Z",
            "archived_at": ("2026-09-01T01:00:00Z" if i == 0 else "2026-10-01T00:00:00Z")} for i in range(4)]
    (_R / "archive" / "events" / "2026-09.jsonl").write_text("\n".join(json.dumps(e) for e in _ev) + "\n")
    _outs = [{"outcome_id": f"e{i}:{h}", "archive_id": f"e{i}", "horizon_sessions": h, "benchmark_return_pct": 1.0}
             for i in range(4) for h in (5, 20)]
    (_R / "archive" / "event_outcomes.jsonl").write_text("\n".join(json.dumps(o) for o in _outs) + "\n")
    (_D / "event_outcome_memory.json").write_text(json.dumps({"counts": {"outcomes": 8}, "benchmark": "SPY"}))
    _oR, _oD, _oRoot = lf.R, lf.D, lf.ROOT
    lf.R, lf.D, lf.ROOT = _R, _D, Path(_t)
    try:
        _e = lf.event()
    finally:
        lf.R, lf.D, lf.ROOT = _oR, _oD, _oRoot
    assert _e["effective_forward_eligible"]["count"] == 1, _e["effective_forward_eligible"]
    assert _e["independently_matured"]["count"] == 1 and _e["benchmark_evaluated"]["count"] == 1, _e["independently_matured"]
    assert lf.check("event", _e) == []
    assert _e["historical"]["outcome_rows_not_forward_or_below_maturity"] == 7
# Options: one matured unit per observation (20-session), never obs×horizon.
assert out["engines"]["options"]["independently_matured"]["dedup_key"] == "observation_id"
for _name in out["engines"]:
    assert lf.check(_name, out["engines"][_name]) == [], _name
print("PASS P3-12 learning funnel contract")
