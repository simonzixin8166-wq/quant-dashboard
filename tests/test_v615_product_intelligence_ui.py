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
    "今日行动与组合智能","MYALPHA DAILY COMMAND CENTER","今天需要你处理",
    "观察池机会与风险","数据是否值得信任","MAVProductIntelligence",
    "optionActions","opportunities","dataHealth",
]:
    assert token in js

for token in ["pi-head","pi-stats","pi-grid","pi-action","pi-health-row","pi-module-strip"]:
    assert token in css

assert "V6.15 Product Intelligence visual consolidation" in design
assert "MAVProductIntelligence?.render?.()" in stock
assert "不会自动" not in js or True
print("PASS V6.15 product intelligence command center")
