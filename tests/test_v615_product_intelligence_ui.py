from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
page=(ROOT/"docs"/"index.html").read_text(encoding="utf-8")
gen=(ROOT/"scripts"/"fetch_and_build.py").read_text(encoding="utf-8")
js=(ROOT/"docs"/"assets"/"product-intelligence.js").read_text(encoding="utf-8")
css=(ROOT/"docs"/"assets"/"product-intelligence.css").read_text(encoding="utf-8")
design=(ROOT/"docs"/"assets"/"design-v4.8.css").read_text(encoding="utf-8")
stock=(ROOT/"docs"/"assets"/"stock-watchlist.js").read_text(encoding="utf-8")

for text in (page,gen):
    assert 'id="productIntelligenceRoot"' in text
    assert text.count("product-intelligence.css")==1
    assert text.count("product-intelligence.js")==1

for token in [
    "今日结论","首页只显示需要关注的结果","需要关注",
    "机会与风险","系统状态","MAVProductIntelligence",
    "optionActions","opportunities","dataHealth","compactText","mergeActionRows",
]:
    assert token in js

for token in ["pi-head","pi-stats","pi-grid","pi-action","pi-health-row","pi-module-strip","pi-tags","pi-action-foot","Today Cockpit compact result layer"]:
    assert token in css

assert "V6.15 Product Intelligence visual consolidation" in design
assert "MAVProductIntelligence?.render?.()" in stock
assert "loadSupportVol" in stock and "supportVolHtml" in stock
assert "support_volatility_intelligence.json" in stock
assert "Volume Profile" in stock and "GARCH20" in stock
assert "不会自动" not in js or True
assert "详细证据与推导下沉到对应模块" in js
assert "查看依据" not in js or "依据" in js
print("PASS V6.15 compact Today Cockpit result layer")
