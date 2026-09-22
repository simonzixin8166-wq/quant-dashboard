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
assert "核心资产预留加仓资金" in generator and "核心资产预留加仓资金" in page
assert 'colspan="14"' in page
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
assert "AbortSignal.timeout(10_000)" in options_function and "UPSTREAM_RATE_LIMIT" in options_function
assert "fetchWithTimeout" in market_function and "X-Cache': 'STALE" in market_function
assert "concurrency:" in workflow and "git pull --rebase origin main" in workflow
stock_targets_rls = (ROOT / "supabase" / "migrations" / "202609220001_stock_targets_private.sql").read_text(encoding="utf-8")
assert "enable row level security" in stock_targets_rls and "stock_targets_admin_update" in stock_targets_rls
assert "期权持仓与风险监控 V2.2" not in generator
assert "期权决策台 V2.2" not in generator

print("test_build_contract.py: all assertions passed")
