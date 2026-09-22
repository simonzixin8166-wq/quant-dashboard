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
stock_targets_rls = (ROOT / "supabase" / "migrations" / "202609220001_stock_targets_private.sql").read_text(encoding="utf-8")
assert "enable row level security" in stock_targets_rls and "stock_targets_admin_update" in stock_targets_rls
assert "期权持仓与风险监控 V2.2" not in generator
assert "期权决策台 V2.2" not in generator

print("test_build_contract.py: all assertions passed")
