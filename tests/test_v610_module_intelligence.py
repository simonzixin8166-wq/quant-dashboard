import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("mi",ROOT/"scripts"/"module_intelligence_engine.py")
mi=importlib.util.module_from_spec(spec);spec.loader.exec_module(mi)

out=mi.build()
assert out["version"]=="6.1.0"
assert out["audit"]["coverage_ok"] is True
assert out["audit"]["actual_tabs"]==14
assert out["audit"]["declared_tabs"]==14
assert out["audit"]["orphan_modules"]==[]

mods={m["id"]:m for m in out["modules"]}
assert mods["tab-finance-tools"]["learning"]=="intentionally_static"
assert mods["tab-options"]["learning"]=="private_only"
assert mods["tab-engine"]["learning"]=="shadow_only"
assert mods["tab-wenxuecity"]["learning"]=="continuous"
assert mods["tab-journal"]["role"]=="outcome_memory"

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
print("PASS V6.1 whole-site module intelligence")

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
