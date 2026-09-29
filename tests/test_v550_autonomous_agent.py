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
assert "Build V5.5 Autonomous Research Agent" in workflow

print("PASS V5.5 Autonomous Research Agent")
