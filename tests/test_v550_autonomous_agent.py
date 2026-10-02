import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from autonomous_research_agent import build_agent, classify_watchlist

data = {
    "updated": "2026-09-29",
    "stocks": {
        "LITE": {"close": 200, "day_chg": 0.12, "rsi": 76, "window_drawdown": -0.03},
        "AAA": {"close": 100, "day_chg": 0.01, "rsi": 55, "window_drawdown": -0.05},
    },
    "core": {},
    "index": {},
    "trend_pulse": {
        "LITE": {"state": "二次启动"},
        "AAA": {"state": "趋势延续"},
    },
}

learning = {
    "situation_memory": [
        {
            "symbol": "LITE",
            "stage": "二次启动",
            "research_priority": 78,
            "contradictions": [],
        },
        {
            "symbol": "AAA",
            "stage": "趋势延续",
            "research_priority": 40,
            "contradictions": [],
        },
    ]
}

previous = {
    "watchlist_attention": [
        {"symbol": "LITE", "stage": "修复中"},
        {"symbol": "AAA", "stage": "趋势延续"},
    ]
}

rows = classify_watchlist(data, learning, previous)
lite = next(row for row in rows if row["symbol"] == "LITE")
aaa = next(row for row in rows if row["symbol"] == "AAA")

assert lite["level"] == "action"
assert lite["timing"] == "今天"
assert any("重大异动" in reason for reason in lite["reasons"])
assert any("Trend Pulse" in reason for reason in lite["reasons"])
assert aaa["level"] == "quiet"

agent = build_agent(data, learning, previous)
assert agent["version"] == "5.5.0"
assert agent["attention_summary"]["counts"]["action"] == 1
assert agent["discovery_queue"][0]["symbol"] == "LITE"
assert agent["private_position_agent"]["mode"] == "browser-private"
assert "不会自动下单" in agent["guardrails"][0]

generator = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")
options_js = (ROOT / "docs" / "assets" / "options-v2.js").read_text(encoding="utf-8")
agent_js = (ROOT / "docs" / "assets" / "autonomous-agent.js").read_text(encoding="utf-8")
workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")

assert 'id="agentAttentionRoot"' in generator
assert 'assets/autonomous-agent.js' in generator
assert 'assets/autonomous-agent.css' in generator
assert "getPositions:()=>[...state.positions.values()]" in options_js
assert "mav:options-updated" in options_js
assert "当前方案：" in agent_js
assert "剩余风险收益：" in agent_js
assert "改变判断的条件" in agent_js
assert "今天优先平仓" in agent_js
assert "未来7天内存在" in agent_js
assert "到期前存在" not in agent_js
assert "Build V5.5 Autonomous Research Agent" in workflow

print("PASS V5.5 Autonomous Research Agent")

assert "V6 Research Planner · 自主研究计划" in agent_js
assert "V7 Shadow Brain · 自我优化" in agent_js
assert "research/research_planner.json" in agent_js
assert "research/self_improvement.json" in agent_js
assert "MYALPHA AUTONOMOUS AGENT · V6 + V7" in agent_js
assert "Build V6 Autonomous Research Planner" in workflow
assert "Build V7 Self-Improvement Shadow Engine" in workflow

assert "V6.2 Research Executor · 自主研究结果" in agent_js
assert "research/research_execution.json" in agent_js
assert "支持证据" in agent_js and "反证" in agent_js and "未知项" in agent_js
assert "Build V6.2 Autonomous Research Executor" in workflow
