from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))
spec = importlib.util.spec_from_file_location("fetch_and_build", ROOT / "scripts" / "fetch_and_build.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

classify = module.classify_stock_status

assert classify(90, 100, 80, .30)[0] == "triggered"
assert classify(104, 100, 20, -.20)[0] == "near"
assert classify(120, 100, 34.99, .30)[0] == "oversold"
assert classify(120, 100, 35, -.101)[0] == "weak"
assert classify(120, 100, 70.01, 0)[0] == "hot"
assert classify(120, 100, 70, .25)[0] == "normal"

no_tier = module.card_etf("SMH", {
    "close": 100.0,
    "drawdown": -.10,
    "rsi": 50.0,
    "dist_200ma": -.02,
    "date": "2026-09-21",
    "tiers": {},
    "ath_is_true": False,
})
assert "不参与核心ETF加仓信号" in no_tier
assert "收盘日线截至：2026-09-21" in no_tier

voo = module.engine_item("VOO", {
    "close": 100.0,
    "ath_is_true": True,
    "ath_validation": "PASS",
    "strategy_drawdown": -.01,
    "window_drawdown": -.01,
    "tiers": module.CORE_TIERS["VOO"],
    "level": 0,
    "level_label": "未触发",
})
assert "1级回撤" in voo and "7.5%" in voo
assert "等待触发 · 不提前加仓" in voo
assert "strategy-tier-grid" in voo

print("test_decision_ui.py: all assertions passed")
