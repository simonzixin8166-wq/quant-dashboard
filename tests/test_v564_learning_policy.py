from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
agent=(ROOT/'docs/assets/autonomous-agent.js').read_text(encoding='utf-8')

assert "mavLearningPolicyV1" in agent
assert "function buildLearningPolicy()" in agent
assert "function applyLearningPolicy(" in agent
assert "restart_bonus" in agent
assert "repeat_alert_penalty" in agent
assert "weak_candidate_penalty" in agent
assert "scope:'research-priority-and-alert-weight-only'" in agent
assert "forceBaseline" in agent
assert "resetLearningPolicy" in agent
assert "resumeLearningPolicy" in agent
assert "Learning Policy · 学习策略" in agent
assert "核心ETF阈值、仓位或交易规则" in agent

# Bounded feedback only; no order execution primitives may be introduced.
for forbidden in ["placeOrder(", "submitOrder(", "autoTrade(", "executeTrade("]:
    assert forbidden not in agent

print("PASS V5.6 Phase 3 auditable learning policy")
