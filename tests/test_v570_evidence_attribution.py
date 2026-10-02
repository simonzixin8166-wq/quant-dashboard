from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
engine_path=ROOT/'scripts/evidence_attribution_engine.py'
spec=importlib.util.spec_from_file_location("ea",engine_path)
ea=importlib.util.module_from_spec(spec); spec.loader.exec_module(ea)

assert ea.VERSION=="5.7.0"
assert "Breadcrumb" in ea.GLOSSARY
assert "False Break" in ea.GLOSSARY
assert "Expected Move" in ea.GLOSSARY
assert "Failure Attribution" in ea.GLOSSARY

early=ea.trend_state({"stage":"趋势启动","weekly":"过渡","contradictions":[]},{})
assert early["state"]=="Early Bull Transition"

confirmed=ea.trend_state({"stage":"二次启动","weekly":"多头","contradictions":[]},{})
assert confirmed["state"]=="Confirmed Trend"

false_break=ea.trend_state({"stage":"修复中","weekly":"过渡","contradictions":[]},{"previous_stage":"趋势启动"})
assert false_break["state"]=="False Break"

attr=ea.attribution_for_event({
    "symbol":"TEST","date":"2026-01-01","stage":"趋势启动","weekly":"过渡","score":70,
    "outcomes":{"20":{"return":-0.12,"mae":-0.15,"mfe":0.03}}
})
assert "trend_false_positive" in attr["tags"]
assert "timeframe_confirmation_missing" in attr["tags"]
assert "large_adverse_move" in attr["tags"]

agent=(ROOT/'docs/assets/autonomous-agent.js').read_text(encoding='utf-8')
assert "MYALPHA AUTONOMOUS AGENT · V6 + V7" in agent
assert "Evidence Map · 证据地图" in agent
assert "Failure Attribution · 错误归因" in agent
assert "这是什么意思：" in agent
assert "为什么重要：" in agent
assert "什么情况会改变判断" in agent
assert "research/evidence_attribution.json" in agent

print("PASS V5.7 evidence attribution learning")


ext=ea.external_outcome_learning({"events":[{
    "event_id":"x","author":"BrightLine","symbol":"NBIS","published_at":"2026-08-18",
    "title":"test","url":"https://example.com",
    "attribution":"author_plan",
    "outcomes":{"20":{"return":-0.12,"mae":-0.18,"mfe":0.04,"excess_vs_qqq":-0.11}},
    "alignment":{"20":"not_aligned"}
}]})
assert ext["mature20"]==1
assert ext["review_candidates"]==1
assert "large_adverse_move" in ext["recent_reviews"][0]["review_tags"]
