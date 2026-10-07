import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ssc",ROOT/"scripts"/"system_status_center.py")
ssc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ssc)

assert ssc.health("success","completed")=="ok"
assert ssc.health("failure","completed")=="bad"
assert ssc.health("cancelled","completed")=="neutral"
assert ssc.health("timed_out","completed")=="bad"
assert ssc.health(None,"in_progress")=="running"
result=ssc.build(fetch_runs=False)
assert result["version"]==4
assert "quant-dashboard" in result["workflows"]
assert "wxc-bot" in result["workflows"]
assert "source_intelligence" in result["artifacts"]
assert "support_volatility_intelligence" in result["artifacts"]
assert "options_opportunity_context" in result["artifacts"]
assert result["principle"]
print("PASS autonomous system status center")

assert result["overall"]=="attention"  # unknown critical workflow state must not look healthy
src=(ROOT/"scripts"/"system_status_center.py").read_text(encoding="utf-8")
assert "per_page=100&page={page}" in src
assert "max_pages=20" in src
assert '"market_dashboard": ROOT/"docs"/"data.json"' in src
assert "research_planner" in result["artifacts"]
assert "self_improvement" in result["artifacts"]
assert "playbook_status" in result["artifacts"]
assert "ledger_anchor" in result["artifacts"]
assert "range_intelligence" in result["artifacts"]
assert "range_research" in result
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
    expected=ssc.expected_completed_us_session(now)
    p.write_text(json.dumps({"generated_at":now.isoformat(),"spy_date":expected}),encoding="utf-8")
    fresh=ssc.artifact_health("market_dashboard",p,now)
    assert fresh["freshness"]=="fresh" and fresh["business_freshness"]=="fresh"
    assert fresh["market_as_of"]==expected and fresh["expected_market_date"]==expected
    assert fresh["decision_eligible"] is True
    research=ssc.artifact_health("range_intelligence",p,now)
    assert research["freshness"]=="fresh"
    assert research["decision_eligible"] is False
    assert research["participation"]=="research_only"
    for research_name in ("support_volatility_intelligence","options_opportunity_context"):
        extra=ssc.artifact_health(research_name,p,now)
        assert extra["decision_eligible"] is False
        assert extra["participation"]=="research_only"
    old_business=(datetime.fromisoformat(expected)-timedelta(days=3)).date().isoformat()
    p.write_text(json.dumps({"generated_at":now.isoformat(),"spy_date":old_business}),encoding="utf-8")
    stale_business=ssc.artifact_health("market_dashboard",p,now)
    assert stale_business["freshness"]=="fresh"
    assert stale_business["business_freshness"]=="stale"
    assert stale_business["decision_eligible"] is False
    p.write_text(json.dumps({"generated_at":(now-timedelta(hours=80)).isoformat(),"spy_date":expected}),encoding="utf-8")
    stale=ssc.artifact_health("market_dashboard",p,now)
    assert stale["freshness"]=="stale" and stale["decision_eligible"] is False
    p.write_text(json.dumps({"generated_at":(now-timedelta(hours=200)).isoformat(),"spy_date":expected}),encoding="utf-8")
    expired=ssc.artifact_health("market_dashboard",p,now)
    assert expired["freshness"]=="expired" and expired["participation"]=="excluded"

# The latest completed US session is business-time aware and skips weekends/NYSE holidays.
assert ssc.is_nyse_session_day(datetime(2026,10,5,tzinfo=timezone.utc).date())
assert not ssc.is_nyse_session_day(datetime(2026,10,4,tzinfo=timezone.utc).date())
# Canonical 16:15 ET completion buffer must match trading_calendar in both DST and standard time.
assert ssc.expected_completed_us_session(datetime(2026,10,6,21,30,tzinfo=timezone.utc))=="2026-10-06"
assert ssc.expected_completed_us_session(datetime(2026,1,5,21,30,tzinfo=timezone.utc))=="2026-01-05"


assert "Autonomous QA & Security" in ssc.WATCH_WORKFLOWS["quant-dashboard"]
assert "decision_data_contract" in result


# Very busy repos can push low-frequency workflows beyond the first 500 runs;
# the default search window must remain deeper than that false-negative boundary.
import inspect
sig=inspect.signature(ssc.github_runs)
assert sig.parameters["max_pages"].default>=10
print("PASS low-frequency workflow pagination depth")
