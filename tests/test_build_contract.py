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
assert 'assets/strategy-budget.js' not in page and 'assets/strategy-budget.js' not in generator
assert "Alpaca Indicative" in generator and "Alpaca Indicative" in page
assert "VIX风险分区半圆仪表盘" in generator and "VIX风险分区半圆仪表盘" in page
assert "年化ROC" in generator and "年化ROC" in page
assert 'id="strategySignalGrid"' in generator
assert "该资产预留资金（USD）" not in generator
assert "strategy-tier-grid" in generator and "只判断是否进入加仓区" in generator
assert "1级回撤" in page and "7.5%" in page
assert "指数、行业与另类资产" in generator and "指数、行业与另类资产" in page
assert "data-stock-row" in generator and "data-stock-row" in page
assert version == "4.4.0"
assert "市场与风险驾驶舱" in generator and "市场与风险驾驶舱" in page
assert "卫星及杠杆" in generator and "卫星及杠杆" in page
assert "不参与核心ETF加仓信号" in generator and "不参与核心ETF加仓信号" in page
assert "收盘日线截至：" in generator and "收盘日线截至：" in page
stock_section = page.split('<div id="tab-stocks"', 1)[1].split('<div id="tab-options"', 1)[0]
assert stock_section.count("<th>") == 8 and "<th>行情详情</th>" not in stock_section
assert "@media (max-width: 680px)" in generator and 'data-label="策略价 / 距离"' in page
assert "等待触发 · 不提前加仓" in generator
assert "rsi < 35" in generator and "dist_200ma < -.10" in generator and "rsi > 70" in generator
assert 'colspan="9"' in page
assert '"hit": drawdown_hit' in generator
assert '"hit": m_score >= 2' not in generator
assert "validate_build_data(data)" in generator and "atomic_write(html_out" in generator
assert "已过期 ·" in (ROOT / "docs" / "assets" / "options-v2.js").read_text(encoding="utf-8")
options_js = (ROOT / "docs" / "assets" / "options-v2.js").read_text(encoding="utf-8")
market_live_js = (ROOT / "docs" / "assets" / "market-live.js").read_text(encoding="utf-8")
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
assert f'assets/roll-manager.js?v={asset_version}' in page and f'assets/roll-manager.css?v={asset_version}' in page
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
assert "restoreArchivedPosition" in options_js and "恢复持仓" in options_js
assert "['closed','expired_worthless','assigned']" in options_js
assert "deletePosition" in options_js and "quick-delete-position" in options_js
assert "输入 DELETE 确认永久删除" in options_js and "属于展期链" in options_js
assert "quick-delete-position" in (ROOT / "docs" / "assets" / "options-v2.css").read_text(encoding="utf-8")
assert "renderPositionTable" in options_js and "option-account-group" in options_js
assert 'id="optionPnlSummary"' in page and "浮盈合计" in options_js and "浮亏合计" in options_js
assert "editPosition" in options_js and 'id="optEditId"' in page
assert "deleteUnderlying" in roll_js and "toggleAccount" in roll_js and "clearObservation" in roll_js
assert "undoRoll" in roll_js and "undo_option_roll_v33" in roll_js
undo_migration = (ROOT / "supabase" / "migrations" / "202609240002_crud_and_roll_undo.sql").read_text(encoding="utf-8")
assert "create or replace function public.undo_option_roll_v33" in undo_migration
assert "NEW_POSITION_ALREADY_CHANGED" in undo_migration and "LATER_ROLL_EXISTS" in undo_migration
assert "deleteTarget" in generator
stock_js = (ROOT / "docs" / "assets" / "stock-watchlist.js").read_text(encoding="utf-8")
stock_function = (ROOT / "supabase" / "functions" / "stock-market" / "index.ts").read_text(encoding="utf-8")
watchlist_migration = (ROOT / "supabase" / "migrations" / "202609240003_stock_watchlist.sql").read_text(encoding="utf-8")
assert f'assets/stock-watchlist.js?v={asset_version}' in page and 'id="stockWatchModal"' in page
assert "stock_watchlist" in stock_js and "StockWatchlist" in stock_js and "删除个股" in stock_js
assert "scope=${scope}" in stock_js and "DAILY_CACHE_KEY" in stock_js and "ensureDaily" in stock_js
assert "stock_watchlist_public_read" in watchlist_migration and "stock_watchlist_admin_delete" in watchlist_migration
assert "Alpaca IEX参考行情" in stock_function and "dist200" in stock_function and "ytdDrawdown" in stock_function
assert "scope === 'quote'" in stock_function and "completedClose/ytdHigh-1" in stock_function
assert "stock-market" in (ROOT / ".github" / "workflows" / "deploy-supabase.yml").read_text(encoding="utf-8")
assert "≤0.995（含）" in page and 'data-buy-zone="sz159307"' in page
assert "option-pnl-account-grid" in options_js and "risk-account-breakdown" in options_js
assert "场外基金接口" not in generator and "Data Status Center" not in generator
assert "数据健康状态" in generator and "普通观察股10分钟" in generator and "期权15分钟" in generator
assert "strategy-budget.js" not in workflow
assert 'class="auth-pending"' in page and "public-access-gate" in page
assert "data-auth-required" in page and "protected-section" in page
assert "noindex,nofollow,noarchive,nosnippet" in page and 'name="referrer" content="no-referrer"' in page
assert "authorized = Boolean" in generator and "该账户没有主理人访问权限" in generator
assert f'assets/site-analytics.js?v={asset_version}' in page and 'id="siteAnalyticsRoot"' in page
analytics_js = (ROOT / "docs" / "assets" / "site-analytics.js").read_text(encoding="utf-8")
analytics_migration = (ROOT / "supabase" / "migrations" / "202609240004_private_gate_analytics.sql").read_text(encoding="utf-8")
assert "record_site_visit_v36" in analytics_js and "get_site_visit_summary_v36" in analytics_js
assert "enable row level security" in analytics_migration and "ADMIN_ONLY" in analytics_migration
assert "No IP address" in analytics_migration and "robots.txt" not in generator
finance_js = (ROOT / "docs" / "assets" / "finance-tools.js").read_text(encoding="utf-8")
finance_css = (ROOT / "docs" / "assets" / "finance-tools.css").read_text(encoding="utf-8")
assert 'id="tab-finance-tools"' in page and "理财工具" in page
assert f'assets/finance-tools.js?v={asset_version}' in page and f'assets/finance-tools.css?v={asset_version}' in page
assert "期末能有多少" in page and "每期需要投入多少" in page and "需要多少年化收益" in page
assert "每个交易日" in page and "每年252次估算" in page
assert "solveYears" in finance_js and "solveRate" in finance_js and "mav_finance_plans_v37" in finance_js
assert "撤回删除" in finance_js and "导出明细 CSV" in page
assert ".finance-tools-shell" in finance_css and ".finance-saved-item" in finance_css
opportunity_js = (ROOT / "docs" / "assets" / "opportunity-radar.js").read_text(encoding="utf-8")
opportunity_css = (ROOT / "docs" / "assets" / "opportunity-radar.css").read_text(encoding="utf-8")
strategy_py = (ROOT / "scripts" / "opportunity_strategy.py").read_text(encoding="utf-8")
assert f'assets/opportunity-radar.js?v={asset_version}' in page and f'assets/opportunity-radar.css?v={asset_version}' in page
assert 'id="tqqqX2Module"' in page and "TQQQ X2 风险敞口" in page
assert 'id="leapsRadarModule"' in page and "LEAPS Call 机会雷达" in page
assert "单次≤1%" in page and "全部LEAPS合计≤3%" in page
assert "不计算金额" in page and "不生成投入金额" in page
assert "hard_exit" in strategy_py and "tier2" in strategy_py and "full_restore" in strategy_py
assert "filterContracts" in opportunity_js and "spread<=.15" in opportunity_js
assert ".opportunity-block" in opportunity_css and ".leaps-card" in opportunity_css
assert "data-risk-todo" in options_js and "策略机会历史" in page
assert "weekend') return null" in market_live_js and "2 * 60 * 60 * 1000" in market_live_js
assert "30 * 60 * 1000" in market_live_js and "周末停止轮询" in page
assert "responseTtl" in market_function and "6 * 60 * 60 * 1000" in market_function
assert "needsProxy" in market_function and "cache.ttlMs" in market_function

manifest = (ROOT / "docs" / "manifest.webmanifest").read_text(encoding="utf-8")
service_worker = (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")
pwa_js = (ROOT / "docs" / "assets" / "pwa.js").read_text(encoding="utf-8")
assert 'rel="manifest"' in page and 'manifest.webmanifest' in page
assert f'assets/pwa.js?v={asset_version}' in page and f'assets/pwa.css?v={asset_version}' in page
assert 'id="pwaInstallButton"' in page and 'id="pwaUpdateBanner"' in page
assert '"display": "standalone"' in manifest and '"purpose": "maskable"' in manifest
assert "SKIP_WAITING" in service_worker and "request.mode==='navigate'" in service_worker
assert "/rest/v1/" in service_worker and "/functions/v1/" in service_worker and "/auth/v1/" in service_worker
assert "beforeinstallprompt" in pwa_js and "controllerchange" in pwa_js
dashboard_css = (ROOT / "docs" / "assets" / "dashboard-v2.2.css").read_text(encoding="utf-8")
assert ".sidebar" in dashboard_css and "overflow-y:auto" in dashboard_css
assert "max-height:860px" in dashboard_css and "scrollbar-width:thin" in dashboard_css
mobile_css = (ROOT / "docs" / "assets" / "mobile-shell.css").read_text(encoding="utf-8")
mobile_js = (ROOT / "docs" / "assets" / "mobile-shell.js").read_text(encoding="utf-8")
assert f'assets/mobile-shell.css?v={asset_version}' in page and f'assets/mobile-shell.js?v={asset_version}' in page
assert 'id="mobileBottomNav"' in page and 'id="mobileNavSheet"' in page
assert "mobile-bottom-nav" in mobile_css and "option-positions-table" in mobile_css
assert "MobileShell" in mobile_js and "tab-overview" in mobile_js and "tab-options" in mobile_js
assert 'class="table-container option-positions-table"' in page

print("test_build_contract.py: all assertions passed")

assert "Trend Pulse" in generator and "tab-trend-pulse" in generator
assert "calculate_trend_pulse" in generator and "Supertrend" in generator and "ADX" in generator
assert (ROOT / "docs" / "assets" / "design-v4.4.css").exists()
