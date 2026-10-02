import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ssc",ROOT/"scripts"/"system_status_center.py")
ssc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ssc)

assert ssc.health("success","completed")=="ok"
assert ssc.health("failure","completed")=="bad"
assert ssc.health(None,"in_progress")=="running"
result=ssc.build(fetch_runs=False)
assert result["version"]==2
assert "quant-dashboard" in result["workflows"]
assert "wxc-bot" in result["workflows"]
assert "source_intelligence" in result["artifacts"]
assert result["principle"]
print("PASS autonomous system status center")

assert result["overall"]=="attention"  # unknown critical workflow state must not look healthy
src=(ROOT/"scripts"/"system_status_center.py").read_text(encoding="utf-8")
assert "per_page=100" in src
assert "research_planner" in result["artifacts"]
assert "self_improvement" in result["artifacts"]
