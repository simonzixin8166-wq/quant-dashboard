from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
journal=(ROOT/'docs/assets/decision-journal.js').read_text(encoding='utf-8')
agent=(ROOT/'docs/assets/autonomous-agent.js').read_text(encoding='utf-8')
options=(ROOT/'docs/assets/options-v2.js').read_text(encoding='utf-8')

assert "mavDecisionJournalV56" in journal
assert "function consolidate(rows)" in journal
assert "transitions" in journal
assert "Agent Error Memory" in journal
assert "getErrorMemory" in journal

assert "mavAgentDecisionMemoryV56" in agent
assert "function remainingEdge(" in agent
assert "Remaining Edge：" in agent
assert "Changed Since Last Decision" in agent
assert "trackDecision" in agent

assert "POSITION DECISION LAB · V5.6" in options
assert "renderPositionDecisionLab" in options
assert "系统只做比较与提醒，不自动交易" in options

# Privacy guard: private option-position details must stay browser-side.
assert "browser-private" not in options
assert "localStorage" in journal
assert "docs/data.json" not in agent

print("PASS V5.6 Autonomous Decision Intelligence")
