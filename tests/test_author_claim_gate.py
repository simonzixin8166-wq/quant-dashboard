"""#133 6117163110 P0-A: unverified author self-reported trades never become learning inputs that change research
priority, error-attribution conclusions or weights. Regression case: BrightLine 202610/7180 (legacy rule: TSLA sell,
author_action/high; ce-5 found no claim)."""
import importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

def mod(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

ea, ex, ee, oe, pl = (mod(n) for n in ("evidence_attribution_engine", "autonomous_research_executor",
                                        "event_evidence_engine", "official_evidence_engine", "autonomous_research_planner"))

# 1) the fail-closed flags that keep these rows out of planner / self-improvement / policy weights are pinned
assert '"external_outcome_evidence_role":"legacy_descriptive_only"' in (ROOT / "scripts/evidence_attribution_engine.py").read_text()
assert '"evidence_role":"legacy_descriptive_only"' in (ROOT / "scripts/method_memory_engine.py").read_text()

# 2) BrightLine-7180-like event: matured, legacy high-confidence "author_action" → review row is unverified, not learning-eligible
bl = {"event_id": "66b4cef06a84cd3de2eb:0:TSLA", "author": "BrightLine", "symbol": "TSLA", "attribution": "author_action",
      "attribution_confidence": "high", "status": "triggered", "published_at": "2026-10-11",
      "outcomes": {"20": {"return": -0.2, "mae": -0.25, "excess_vs_qqq": -0.2}}, "alignment": {"20": "not_aligned"}}
neg_third = {**bl, "event_id": "x:1:NVDA", "symbol": "NVDA", "attribution": "third_party_example"}
neg_unconf = {**bl, "event_id": "x:2:NVDA", "symbol": "NVDA", "attribution": "unconfirmed_author_context"}
out = ea.external_outcome_learning({"events": [bl, neg_third, neg_unconf]})
rows = out["recent_reviews"]
assert [r["symbol"] for r in rows] == ["TSLA"], "third-party examples and unconfirmed context never become reviews"
assert rows[0]["verification_status"] == "unverified_author_self_report" and rows[0]["learning_eligible"] is False

evidence = {"external_outcome_evidence_role": "legacy_descriptive_only",
            "failure_attribution": {"external_outcome_reviews": rows}}
# 3) planner: no failure_review task from these rows
plan = pl.build({}, {}, evidence, {"evidence_role": "legacy_descriptive_only"}, {}, {})
tasks = (plan.get("today") or []) + (plan.get("queue") or []) + (plan.get("tasks") or [])
assert not any(t.get("kind") == "failure_review" for t in tasks), "planner must not schedule failure reviews from unverified author claims"
# 4) executor: rows are background (unknowns), never counter-evidence
support, counter, unknowns = ex.market_brief({"key": "TSLA"}, {}, evidence, {}, {})
assert not any("反例" in c or "失效样本" in c for c in counter), counter
assert any("未经核实" in u for u in unknowns), unknowns
fs, fc, fu = ex.failure_brief({"key": "TSLA"}, evidence, {})
assert not any("失败/反例样本" in x for x in fs) and any("未经核实" in u for u in fu)
# 5) evidence engines: unverified rows do not select symbols for collection
assert "TSLA" not in ee.selected_symbols({}, evidence)
assert "TSLA" not in oe.selected_symbols({}, evidence)
# rows from an older evidence file (no learning_eligible field) are also excluded — fail closed
old = {"failure_attribution": {"external_outcome_reviews": [{"symbol": "TSLA"}]}}
assert "TSLA" not in ee.selected_symbols({}, old) and "TSLA" not in oe.selected_symbols({}, old)

# 6) audit over the real repo: every path gated; BrightLine 7180 case recorded as UNKNOWN, not denied
au = mod("author_claim_contamination_audit")
rep = au.build()
assert rep["all_gated"] is True, [g for g in rep["gates"] if g["gated"] is not True]
assert "UNKNOWN" in rep["case_brightline_7180"]["note"]
print("test_author_claim_gate OK")
