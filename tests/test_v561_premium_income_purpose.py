from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
builder=(ROOT/'scripts/fetch_and_build.py').read_text(encoding='utf-8')
html=(ROOT/'docs/index.html').read_text(encoding='utf-8')
js=(ROOT/'docs/assets/options-v2.js').read_text(encoding='utf-8')
needle='主要赚取权利金，尽量避免被指派'
assert needle in builder
assert needle in html
assert "premium_income" in js
assert "权利金优先" in js
assert "尽量避免被指派" in js
print("PASS premium-income purpose")
