from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ui=(ROOT/"docs/assets/knowledge.js").read_text(encoding="utf-8")

assert "research/method_memory.json" in ui
assert "方法验证状态 · 自动学习" in ui
assert "Direct links" in ui
assert "direct_developing" in ui
assert "outcome_supportive" in ui
assert "outcome_mixed" in ui
assert "outcome_challenging" in ui
assert "Research Only · 状态由 Method Memory 自动更新，不自动修改正式交易规则。" in ui
assert "cache:'no-store'" in ui
assert "loadMethodMemory()" in ui

print("PASS V6.13.4 dynamic Method Memory evidence UI")
