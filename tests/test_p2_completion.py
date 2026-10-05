from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]

journal=(ROOT/"docs"/"assets"/"decision-journal.js").read_text(encoding="utf-8")
assert "实际操作与错误归因" in journal
assert "updateOperatorDecision" in journal
for token in ["system_error","user_decision_error","data_error","market_randomness","correct_process"]:
    assert token in journal

guard=(ROOT/"scripts"/"private_guardrail.py").read_text(encoding="utf-8")
for name in [
    "system_status.json","official_evidence.json","event_evidence.json",
    "autonomous_agent.json","research_execution.json","controlled_learning_policy.json",
    "source_rule_lifecycle.json",
]:
    assert name in guard

daily=(ROOT/".github"/"workflows"/"daily.yml").read_text(encoding="utf-8")
assert "python -m compileall -q scripts" in daily
assert "python -m py_compile scripts/app_version.py" not in daily

builder=(ROOT/"scripts"/"fetch_and_build.py").read_text(encoding="utf-8")
assert "from dashboard_universe import" in builder
assert "from dashboard_option_math import" in builder
assert "def norm_cdf(" not in builder
assert "STOCK_META = {" not in builder

spec=importlib.util.spec_from_file_location("mathmod",ROOT/"scripts"/"dashboard_option_math.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
g=m.calc_option_greeks(100,100,1,0.03,0.2,"call")
assert 0<g["delta"]<1 and g["gamma"]>0
assert m.build_yahoo_option_ticker("IREN","2026-12-18","put",65)=="IREN261218P00065000"

storage=(ROOT/"scripts"/"research_storage_health.py").read_text(encoding="utf-8")
assert "no pruning before reader-compatible partition migration" in storage
assert "5_000_000" in storage

print("PASS P2 completion contract")
