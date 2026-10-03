from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
watch=(ROOT/"docs/assets/stock-watchlist.js").read_text(encoding="utf-8")
qa=(ROOT/"docs/assets/autonomous-qa.js").read_text(encoding="utf-8")
css=(ROOT/"docs/assets/design-v4.8.css").read_text(encoding="utf-8")
browser=(ROOT/"scripts/autonomous_site_qa.mjs").read_text(encoding="utf-8")

expected={
 "AVGO":"博通",
 "ORCL":"甲骨文",
 "TSM":"台积电",
 "MRVL":"迈威尔科技",
 "AMD":"美国超微公司",
 "SOFI":"SoFi Technologies",
 "NBIS":"NEBIUS",
 "LITE":"Lumentum",
}
for symbol,name in expected.items():
    assert f"{symbol}:'{name}'" in watch, (symbol,name)

assert "canonicalDisplayName(symbol,item.display_name)" in watch
for raw in ["research_planner","learning_engine","self_improvement","system_status","decision_journal","failure_attribution"]:
    assert f"'{raw}':" in qa
assert ".map(humanNode)" in qa
assert "影子学习" in qa and "仅Shadow" not in qa

assert "overflow-x:auto!important" in css
assert ".stock-table .stock-name{font-size:16px" in css
assert "module_english_leak" in browser
assert "bad_canonical_names" in browser
assert "body_overflow_px" in browser
assert "themeToggle" in browser

print("PASS V6.9 full UI hardening")
