import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from evaluation_spec import direction_adjusted_return,unconditional_lift
from research_boundary_guard import snapshot,check_changed_paths,check_allowed_paths,check_evidence_lock

assert direction_adjusted_return("bearish",-0.10)==0.10
assert direction_adjusted_return("bullish",0.10)==0.10
assert abs(unconditional_lift("bullish",0.10,0.10))<1e-12
assert check_changed_paths(["config/x.json"])==["config/x.json"]
assert check_changed_paths(["research/state/x.json"])==[]
assert check_allowed_paths(["research/state/x.json"])==[]
# Negative injection: any write outside research/ must be rejected.
assert check_allowed_paths(["config/injected.json"])==["config/injected.json"]
assert check_allowed_paths(["docs/data/injected.json"])==["docs/data/injected.json"]
lock=json.loads((ROOT/"config/research_evidence_lock.json").read_text())
assert len(lock.get("locked_research_specs") or {})>=6
assert "research/specs/v616_readiness_spec.json" in lock["locked_research_specs"]
assert "research/specs/entry_semantics_registry.json" in lock["locked_research_specs"]
assert "research/specs/component_registry.json" in lock["locked_research_specs"]
spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
assert spec["spec_version"]=="1.6"
assert spec["thresholds"]["provisional"] is True
assert spec["change_policy"]["forbid_tuning_to_pass_named_methods"] is True
assert spec["definitions"]["promotion_unit"]=="rule_family"
assert spec["definitions"]["multiple_testing"]["fdr_method"]=="Benjamini-Hochberg"
assert spec["promotion_activation"]["state"]=="shadow_until_statistical_controls_revalidated_under_spec_1_6"
assert spec["definitions"]["rule_family_definition_version"]=="1.3"
assert spec["definitions"]["clustering"]["event_effective_unit"]=="symbol x overlap-connected realized-horizon cluster"
assert "transitively overlapping" in spec["definitions"]["clustering"]["time_cluster_definition"]
assert spec["definitions"]["multiple_testing"]["untestable_hypothesis_pvalue_for_fdr"]==1.0
assert spec["definitions"]["primary_exclusion_precedence"][0]=="non_point_in_time_source"
assert spec["definitions"]["scoring_engine_identity"]["semantic_change_requires_new_spec_version"] is True
assert spec["definitions"]["mae_noninferiority"]["margin"]==0.0
assert spec["thresholds"]["max_single_symbol_effective_unit_share"]==0.40
pit=spec["definitions"]["point_in_time_eligibility"]
assert pit["comparison"]=="baseline_timestamp_utc > first_fetched_at_utc"
assert pit["equality_policy"]=="fail_closed_not_eligible"
assert pit["evidence_foundation_start_utc"]=="2026-10-04T00:00:00+00:00"
assert check_evidence_lock()==[]
print("PASS V6.15.0 evaluation spec and boundary guard")

# Legacy Method Memory must not classify a successful bearish decline as failure,
# and market context must stop strictly before the baseline date.
legacy=(ROOT/"scripts"/"method_memory_engine.py").read_text(encoding="utf-8")
assert 'work=q[q.index < d].copy()' in legacy
assert 'if outcome and align=="not_aligned":' in legacy
assert 'align=="not_aligned" or finite(outcome.get("return"))' not in legacy

workflow=(ROOT/".github/workflows/research-evidence-update.yml").read_text(encoding="utf-8")
assert "--assert-worktree-research-only" in workflow
assert "--assert-staged-research-only" in workflow
assert "grep -Ev" not in workflow
assert "|| true" not in workflow
