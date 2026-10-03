import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("mi",ROOT/"scripts"/"module_intelligence_engine.py")
mi=importlib.util.module_from_spec(spec);spec.loader.exec_module(mi)

out=mi.build()
assert out["version"]=="6.8.2"
assert out["audit"]["coverage_ok"] is True
assert out["audit"]["actual_tabs"]==15
assert out["audit"]["declared_tabs"]==15
assert out["audit"]["orphan_modules"]==[]
assert out["audit"]["navigation_model_ok"] is True
assert out["audit"]["primary_count"]==8
assert out["audit"]["auxiliary_count"]==2
assert out["audit"]["secondary_count"]==5
assert "tab-agent-center" in out["audit"]["primary_tabs"]

mods={m["id"]:m for m in out["modules"]}
assert mods["tab-finance-tools"]["learning"]=="intentionally_static"
assert mods["tab-options"]["learning"]=="private_only"
assert mods["tab-engine"]["learning"]=="shadow_only"
assert mods["tab-wenxuecity"]["learning"]=="continuous"
assert mods["tab-journal"]["role"]=="outcome_memory"
assert mods["tab-agent-center"]["role"]=="agent_brain"

for m in out["modules"]:
    assert m["purpose"]
    assert m["inputs"]
    assert m["outputs"]
    assert m["learning"]
    assert m["why_it_exists"]
    assert m["guardrail"]

assert any(e["from"]=="tab-wenxuecity" and e["to"]=="method_memory" for e in out["edges"])
assert "V6 Research Planner" in out["agent_loop"]
assert "V7 Candidate + Shadow Brain" in out["agent_loop"]
print("PASS V6.6 whole-site module intelligence and IA tiers")

services={s["id"]:s for s in out["services"]}
assert services["research-executor"]["role"]=="evidence_synthesis"
assert "research_execution" in out["artifacts"]
assert "V6.2 Research Executor" in out["agent_loop"]

assert services["official-evidence"]["role"]=="primary_source"
assert "official_evidence" in out["artifacts"]
assert "V6.3 Official Evidence Layer" in out["agent_loop"]

assert services["event-window-attribution"]["role"]=="failure_context"
assert "event_window_attribution" in out["artifacts"]
assert "V6.5 Event Window Attribution" in out["agent_loop"]

assert services["cross-asset-divergence"]["role"]=="macro_market_divergence"
assert "cross_asset_divergence" in out["artifacts"]
assert "cross_asset_divergence_history" in out["artifacts"]

assert services["breadth-intelligence"]["role"]=="market_participation"
assert services["regime-combination-memory"]["role"]=="joint_situation_memory"
for key in ["breadth_intelligence","breadth_intelligence_history","regime_combination_memory","regime_combination_history"]:
    assert key in out["artifacts"]

assert services["leverage-rebound-intelligence"]["role"]=="leverage_context"
assert services["leverage-rebound-intelligence"]["learning"]=="shadow_only"
assert "research_planner" in services["leverage-rebound-intelligence"]["outputs"]
assert "research_executor" in services["leverage-rebound-intelligence"]["outputs"]
