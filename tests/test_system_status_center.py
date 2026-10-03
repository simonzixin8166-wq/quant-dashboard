import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ssc",ROOT/"scripts"/"system_status_center.py")
ssc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ssc)

assert ssc.health("success","completed")=="ok"
assert ssc.health("failure","completed")=="bad"
assert ssc.health(None,"in_progress")=="running"
result=ssc.build(fetch_runs=False)
assert result["version"]==4
assert "quant-dashboard" in result["workflows"]
assert "wxc-bot" in result["workflows"]
assert "source_intelligence" in result["artifacts"]
assert result["principle"]
print("PASS autonomous system status center")

assert result["overall"]=="attention"  # unknown critical workflow state must not look healthy
src=(ROOT/"scripts"/"system_status_center.py").read_text(encoding="utf-8")
assert "per_page=100&page={page}" in src
assert "max_pages=5" in src
assert '"market_dashboard": ROOT/"docs"/"data.json"' in src
assert "research_planner" in result["artifacts"]
assert "self_improvement" in result["artifacts"]
assert "playbook_status" in result["artifacts"]
assert "ledger_anchor" in result["artifacts"]
assert "playbook_runtime" in result

# Busy repositories may push watched workflows beyond the first 100 runs.
assert ssc.latest_by_name(
    [{"name":"pages build and deployment","status":"completed","conclusion":"success"}]*100
    + [{"name":"Daily Dashboard Update","status":"completed","conclusion":"success"}],
    ["Daily Dashboard Update"],
)["Daily Dashboard Update"]["conclusion"]=="success"


# Freshness contract: fresh artifacts may participate; stale/expired ones are excluded.
from datetime import datetime, timezone, timedelta
import tempfile, json
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"artifact.json"
    now=datetime.now(timezone.utc)
    p.write_text(json.dumps({"generated_at":now.isoformat()}),encoding="utf-8")
    fresh=ssc.artifact_health("market_dashboard",p,now)
    assert fresh["freshness"]=="fresh" and fresh["decision_eligible"] is True
    p.write_text(json.dumps({"generated_at":(now-timedelta(hours=80)).isoformat()}),encoding="utf-8")
    stale=ssc.artifact_health("market_dashboard",p,now)
    assert stale["freshness"]=="stale" and stale["decision_eligible"] is False
    p.write_text(json.dumps({"generated_at":(now-timedelta(hours=200)).isoformat()}),encoding="utf-8")
    expired=ssc.artifact_health("market_dashboard",p,now)
    assert expired["freshness"]=="expired" and expired["participation"]=="excluded"

assert "Autonomous QA & Security" in ssc.WATCH_WORKFLOWS["quant-dashboard"]
assert "decision_data_contract" in result
