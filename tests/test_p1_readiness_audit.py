"""#133 6117308392: P1 readiness audit invariants (read-only; real repository)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import p1_readiness_audit as a  # noqa: E402

rep = a.build()
p = rep["precedents"]
# B1 sources: no usable precedent may have an outcome window closing after the memory date; VIX never a precedent
assert p["look_ahead_violations"] == 0
assert all(v["excluded"].get("look_ahead_window_after_memory_date", 0) == 0 for v in p["per_symbol"].values())
assert p["source_sha256"] and p["case_id_rule"]
# six outcome memories always get one of the agreed verdicts, with a reason when not eligible
allowed = {"eligible_for_b2_clean_subset_only", "pending", "insufficient", "blocked"}
assert set(rep["outcome_verdicts"]) == {"company_fundamental_outcome_memory", "event_outcome_memory", "support_volatility_outcome_memory",
                                        "options_opportunity_outcome_memory", "macro_outcome_memory", "market_state_outcome_scorecards"}
assert set(rep["outcome_verdicts"].values()) <= allowed
for k, v in rep["outcomes"].items():
    if v["verdict"] == "blocked":
        assert v.get("reason"), k
f = rep["outcomes"]["company_fundamental_outcome_memory"]
assert f["duplicate_outcome_keys"] == 0
if f["verdict"].startswith("eligible"):
    assert min(f["clean_matured_outcomes"].get(20, 0), f["clean_matured_outcomes"].get(60, 0)) >= rep["b2_min_matured_per_horizon"]
    assert sum(f["clean_matured_outcomes"].values()) < sum(f["matured_outcomes"].values()) or f["contaminated_observations"] == 0
# candidates: recommendations never say delete
assert all(not r.startswith("delete") for r in rep["candidates"]["recommendation"].values())
assert rep["read_only"] is True and rep["learning_state"] == "UNPROVEN"
print("test_p1_readiness_audit OK")
