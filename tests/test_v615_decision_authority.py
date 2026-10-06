from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

pi=(ROOT/"docs/assets/product-intelligence.js").read_text(encoding="utf-8")
assistant=(ROOT/"docs/assets/investment-assistant.js").read_text(encoding="utf-8")
qa=(ROOT/"scripts/autonomous_site_qa.mjs").read_text(encoding="utf-8")
status=(ROOT/"scripts/system_status_center.py").read_text(encoding="utf-8")

assert "function decisionAuthority()" in pi
assert "market.business_freshness==='fresh'" in pi
assert "expected_market_date" in pi
assert "mav:decision-authority" in pi

assert "AI 投资助手 · 等待数据恢复" in assistant
assert "今日驾驶舱是唯一执行结论" in assistant
assert "if(!authority.decision_eligible)" in assistant

assert "report.business_data" in qa
assert "business_freshness==='fresh'" in qa
assert "marketAsOf===expected" in qa

assert "expected_completed_us_session" in status
assert "market_business_freshness" in status
assert 'blocked_by"]="market_dashboard_business_freshness"' in status
assert "market_as_of" in status and "expected_market_date" in status

print("PASS single decision authority + business-date freshness contract")
