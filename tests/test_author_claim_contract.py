"""#133 6117308392 / #205 cross-consumer contract: every script that reads author outcome reviews or legacy
operation cases must apply the gate (legacy flag, learning_eligible filter, or explicit unverified labelling).
A new consumer that reads them without a gate fails CI."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
GATES = ('legacy_descriptive_only', 'learning_eligible', '未经核实', 'unverified_author_self_report')
SENSITIVE = ('external_outcome_reviews', 'external_failure_candidates', 'owned_operation_cases')
PRODUCERS = {'evidence_attribution_engine.py', 'source_intelligence_engine.py', 'author_claim_contamination_audit.py'}
DESCRIPTIVE_OK = {  # reviewed: these read the keys only for counting/archiving/consistency checks, never for priority or weights
    'source_history_cache.py', 'v615_step0_audit.py', 'v615_rule_registry.py', 'data_learning_coverage_audit.py',
}
bad = []
for p in sorted((ROOT / "scripts").glob("*.py")):
    s = p.read_text(encoding="utf-8", errors="ignore")
    if p.name in PRODUCERS or not any(k in s for k in SENSITIVE):
        continue
    if p.name in DESCRIPTIVE_OK:
        continue
    if not any(g in s for g in GATES):
        bad.append(p.name)
assert not bad, f"ungated consumers of unverified author claims: {bad}"
print("test_author_claim_contract OK")
