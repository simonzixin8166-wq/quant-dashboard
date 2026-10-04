import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from research_boundary_guard import snapshot,check_manifest_completeness,check_allowed_paths,check_evidence_lock

assert check_manifest_completeness()==[]
assert check_evidence_lock()==[]
snap=snapshot()
assert snap["manifest_version"]=="1.0"
files=snap["files"]
assert "config/playbooks.public.json" in files
assert "scripts/playbook_config.py" in files
assert "scripts/fetch_and_build.py" in files
assert "scripts/autonomous_research_planner.py" in files
assert "docs/research/ledger_anchor.json" in files

# Negative write injection must be rejected by the allowlist.
assert check_allowed_paths(["research/audit/x.json"])==[]
assert check_allowed_paths(["docs/data/injected.json"])==["docs/data/injected.json"]
assert check_allowed_paths(["config/research_evidence_lock.json"])==["config/research_evidence_lock.json"]

workflow=(ROOT/".github/workflows/research-evidence-update.yml").read_text(encoding="utf-8")
assert "permissions:\n      contents: read" in workflow
assert "permissions:\n      contents: write" in workflow
assert "actions/upload-artifact@v4" in workflow
assert "actions/download-artifact@v4" in workflow
for step in [
 "rule_registry","rule_family","source_store","event_score","observational_events","stooq_coverage","method_attribution",
 "event_history","rule_scorecard","family_scorecard","contradiction_memory","promotion_gate",
 "statistical_controls","spec_coexistence","component_manifest","v616_readiness","monthly_evidence_audit"
]:
    assert f"--name {step}" in workflow
print("PASS V6.15.8a per-step production invariant / split workflow permissions")
