from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
js=(ROOT/"docs/assets/autonomous-agent.js").read_text(encoding="utf-8")
manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
status=(ROOT/"scripts/system_status_center.py").read_text(encoding="utf-8")

for path in ["research/breadth_intelligence.json","research/regime_combination_memory.json"]:
    assert path in js
assert "Breadth Intelligence · 市场参与度" in js
assert "Regime Combination Memory · 组合情境记忆" in js
assert "市场参与度与跨资产环境" in js
assert "SPY-RSP" in js and "QQQ-QQQE" in js
assert "breadth_intelligence.json" in manifest
assert "regime_combination_memory.json" in manifest
assert "breadth_intelligence" in status
assert "regime_combination_memory" in status
print("PASS V6.8 breadth/regime UI wiring")

assert "A/D20" in js
assert "52周新高" in js
assert "20日MAE" in js and "20日MFE" in js
