import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ssc",ROOT/"scripts"/"system_status_center.py")
ssc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ssc)

assert ssc.health("success","completed")=="ok"
assert ssc.health("failure","completed")=="bad"
assert ssc.health(None,"in_progress")=="running"
result=ssc.build(fetch_runs=False)
assert result["version"]==1
assert "quant-dashboard" in result["workflows"]
assert "wxc-bot" in result["workflows"]
assert "source_intelligence" in result["artifacts"]
assert result["principle"]
print("PASS autonomous system status center")
