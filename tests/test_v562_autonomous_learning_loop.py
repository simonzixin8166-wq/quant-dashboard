from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
agent=(ROOT/'docs/assets/autonomous-agent.js').read_text(encoding='utf-8')
journal=(ROOT/'docs/assets/decision-journal.js').read_text(encoding='utf-8')
options=(ROOT/'docs/assets/options-v2.js').read_text(encoding='utf-8')
css=(ROOT/'docs/assets/options-v2.css').read_text(encoding='utf-8')

assert "mavAgentDecisionMemoryV562" in agent
assert "decisionHistory" in agent
assert "version:'v2'" in agent
assert "strikeBuffer" in agent
assert "premiumPriority" in agent
assert "What I learned · 自主学习" in agent
assert "MYALPHA AUTONOMOUS AGENT · V6 + V7" in agent

assert "function weeklySelfReview(rows)" in journal
assert "Weekly Self Review · 每周自主复盘" in journal
assert "getSelfReview" in journal
assert "只影响研究优先级" in journal

assert "option-card-decision" in options
assert "当前动作" in options
assert "Remaining Edge" in options
assert ".option-card-decision" in css

# Guardrails must remain explicit.
assert "不会自动下单" in agent
print("PASS V5.6 Phase 2 autonomous learning loop")
