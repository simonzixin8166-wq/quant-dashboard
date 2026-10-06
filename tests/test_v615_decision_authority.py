from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

pi=(ROOT/"docs/assets/product-intelligence.js").read_text(encoding="utf-8")
assistant=(ROOT/"docs/assets/investment-assistant.js").read_text(encoding="utf-8")
qa=(ROOT/"scripts/autonomous_site_qa.mjs").read_text(encoding="utf-8")
status=(ROOT/"scripts/system_status_center.py").read_text(encoding="utf-8")
server=(ROOT/"scripts/server_action_engine.py").read_text(encoding="utf-8")
workflow=(ROOT/".github/workflows/autonomous-qa.yml").read_text(encoding="utf-8")

assert "function decisionAuthority()" in pi
assert "market.business_freshness==='fresh'" in pi
assert "expected_market_date" in pi
assert "mav:decision-authority" in pi
assert "systemLoaded:false" in pi and "serverLoaded:false" in pi
assert "statusAgeHours<=30" in pi
assert "market.market_as_of===market.expected_market_date" in pi
assert "return [{priority:120" in pi  # blocked mode must not retain stale action rows

assert "AI 投资助手 · 等待数据恢复" in assistant
assert "今日驾驶舱是唯一执行结论" in assistant
assert "if(!authority.decision_eligible)" in assistant
assert "decision_eligible:false,title:'今日无法可靠判断'" in assistant

assert "report.business_data" in qa
assert "business_freshness==='fresh'" in qa
assert "marketAsOf===expected" in qa
assert "process.env.EXPECTED_MARKET_DATE" in qa
assert "statusAgeHours<=30" in qa
assert "report.server_action" in qa
assert "report.engineering_qa" in qa
assert "report.investment_data_qa" in qa
assert "report.decision_readiness" in qa
assert "report.overall=report.decision_readiness.status" in qa

assert "expected_completed_us_session" in status
assert "trading_calendar.expected_latest_completed_session" in status
assert "market_business_freshness" in status
assert 'blocked_by"]="market_dashboard_business_freshness"' in status
assert "market_as_of" in status and "expected_market_date" in status

assert "trading_calendar.expected_latest_completed_session" in server
assert "age_hours<=30" in server
assert 'DATA=ROOT/"docs"/"data.json"' in server
assert "quote_freshness_cutoff" in server
assert "last_checked_at" in server
assert "schedule:" in workflow and "EXPECTED_MARKET_DATE" in workflow

print("PASS single decision authority + business-date freshness contract")
