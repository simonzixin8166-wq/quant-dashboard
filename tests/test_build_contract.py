from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
generator = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")
page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

version = re.search(r'^APP_VERSION = "([^"]+)"', generator, re.M).group(1)
asset_version = re.search(r'^ASSET_VERSION = "([^"]+)"', generator, re.M).group(1)

assert f'data-app-version="{version}"' in page
assert f'assets/options-v2.js?v={asset_version}' in page
assert f'assets/market-live.js?v={asset_version}' in page
assert f'assets/strategy-budget.js?v={asset_version}' in page
assert "Alpaca Indicative" in generator and "Alpaca Indicative" in page
assert "VIX风险分区半圆仪表盘" in generator and "VIX风险分区半圆仪表盘" in page
assert "年化ROC" in generator and "年化ROC" in page
assert 'id="strategyBudgetGrid"' in generator and 'id="strategyBudgetGrid"' in page
assert page.count('id="strategyBudgetGrid"') == 1
assert "该资产预留资金（USD）" in generator and "该资产预留资金（USD）" in page
assert "一级7.5%" in page
assert "指数、行业与另类资产" in generator and "指数、行业与另类资产" in page
assert "data-stock-row" in generator and "data-stock-row" in page
assert version == "3.2"
assert "市场与风险驾驶舱" in generator and "市场与风险驾驶舱" in page
assert "卫星及杠杆" in generator and "卫星及杠杆" in page
assert "不参与核心ETF加仓信号" in generator and "不参与核心ETF加仓信号" in page
assert "收盘日线截至：" in generator and "收盘日线截至：" in page
stock_section = page.split('<div id="tab-stocks"', 1)[1].split('<div id="tab-options"', 1)[0]
assert stock_section.count("<th>") == 7 and "<th>行情详情</th>" not in stock_section
assert "@media (max-width: 680px)" in generator and 'data-label="策略价 / 距离"' in page
assert "等待：不提前加仓" in generator and "等待：不提前加仓" in page
assert "rsi < 35" in generator and "dist_200ma < -.10" in generator and "rsi > 70" in generator
assert 'colspan="9"' in page
assert '"hit": drawdown_hit' in generator
assert '"hit": m_score >= 2' not in generator
assert "validate_build_data(data)" in generator and "atomic_write(html_out" in generator
assert "已过期 ·" in (ROOT / "docs" / "assets" / "options-v2.js").read_text(encoding="utf-8")
options_js = (ROOT / "docs" / "assets" / "options-v2.js").read_text(encoding="utf-8")
market_live_js = (ROOT / "docs" / "assets" / "market-live.js").read_text(encoding="utf-8")
budget_js = (ROOT / "docs" / "assets" / "strategy-budget.js").read_text(encoding="utf-8")
options_function = (ROOT / "supabase" / "functions" / "options-market" / "index.ts").read_text(encoding="utf-8")
market_function = (ROOT / "supabase" / "functions" / "market-snapshot" / "index.ts").read_text(encoding="utf-8")
workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
assert 'id="refreshAllOptions"' in page and "refreshAllPositions" in options_js
assert "休市 · 上次报价" in options_js and "POSITION_REFRESH_MS=15*60*1000" in options_js
assert "document.visibilityState" in options_js and "document.visibilityState" in market_live_js
assert 'id="optionLifecycleModal"' in page and 'id="optionHistoryBody"' in page
assert "realizedPnl" in options_js and "assignmentBasis" in options_js
assert "deleteOptionPosition" not in page and "deleteOptionPosition" not in generator
close_migration = (ROOT / "supabase" / "migrations" / "202609220002_options_close_workflow.sql").read_text(encoding="utf-8")
assert "close_notes" in close_migration and "settlement_stock_price" in close_migration
assert "const saveTimers=new Map()" in budget_js
assert "回撤幅度还差" in budget_js
decision_js = (ROOT / "docs" / "assets" / "dashboard-v2.2.js").read_text(encoding="utf-8")
assert "global.StockDecision" in decision_js and "sortStocks('priority')" in decision_js
assert "const rank={triggered:0,near:1,oversold:2,weak:3,hot:4,normal:5}" in decision_js
assert "rsi<35" in decision_js and "dist<-.10" in decision_js and "rsi>70" in decision_js
assert "hasValue=target!==null" in decision_js
assert "AbortSignal.timeout(10_000)" in options_function and "UPSTREAM_RATE_LIMIT" in options_function
assert "fetchWithTimeout" in market_function and "X-Cache': 'STALE" in market_function
assert "concurrency:" in workflow and "git pull --rebase origin main" in workflow
stock_targets_rls = (ROOT / "supabase" / "migrations" / "202609220001_stock_targets_private.sql").read_text(encoding="utf-8")
assert "enable row level security" in stock_targets_rls and "stock_targets_admin_update" in stock_targets_rls
assert "期权持仓与风险监控 V2.2" not in generator
assert "期权决策台 V2.2" not in generator
roll_js = (ROOT / "docs" / "assets" / "roll-manager.js").read_text(encoding="utf-8")
roll_css = (ROOT / "docs" / "assets" / "roll-manager.css").read_text(encoding="utf-8")
roll_migration = (ROOT / "supabase" / "migrations" / "202609230001_option_roll_manager.sql").read_text(encoding="utf-8")
assert 'assets/roll-manager.js?v=3.2' in page and 'assets/roll-manager.css?v=3.2' in page
assert 'id="rollManagerRoot"' in page and "分账户期权与展期管理" in page
assert "classifyRoll" in roll_js and "record_option_roll_v32" in roll_js
assert "option_underlyings" in roll_migration and "option_roll_journal" in roll_migration
assert "put_watch_delta" in roll_migration and "put_assignment_mode" in roll_migration
assert "for update" in roll_migration.lower() and "record_option_roll" in roll_migration
assert ".roll-position" in roll_css
assert 'id="putWatch"' in page and 'id="putAssignmentMode"' in page
assert "收盘Delta待更新" in roll_js and "接货/展期二选一" in roll_js
multi_account_migration = (ROOT / "supabase" / "migrations" / "202609240001_multi_account_options.sql").read_text(encoding="utf-8")
assert "broker_accounts" in multi_account_migration and "broker_account_id" in multi_account_migration
assert "record_option_roll_v32" in multi_account_migration and "p_roll_qty" in multi_account_migration
assert 'id="accountModal"' in page and 'id="rollQty"' in page and 'id="optBrokerAccount"' in page
assert "availableCoveredShares" in roll_js and "accountPositions" in roll_js
assert "previous_regular_close" in market_function and "meta.chartPreviousClose" not in market_function

print("test_build_contract.py: all assertions passed")
