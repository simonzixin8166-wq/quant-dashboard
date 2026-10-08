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
print("PASS P3-12 learning funnel contract")
