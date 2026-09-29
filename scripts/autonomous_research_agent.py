#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "docs" / "data.json"
LEARNING = ROOT / "docs" / "research" / "learning_engine.json"
PREVIOUS = ROOT / "docs" / "research" / "autonomous_agent.json"
OUT = PREVIOUS
VERSION = "5.5.0"

LEVEL_RANK = {"quiet": 0, "watch": 1, "review": 2, "action": 3}


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def prior_stage_map(previous: dict) -> Dict[str, str]:
    out = {}
    for row in previous.get("watchlist_attention") or []:
        if row.get("symbol"):
            out[row["symbol"]] = row.get("stage") or ""
    return out


def classify_watchlist(data: dict, learning: dict, previous: dict) -> List[dict]:
    situations = {
        row.get("symbol"): row
        for row in (learning.get("situation_memory") or [])
        if row.get("symbol")
    }
    prior = prior_stage_map(previous)
    rows = []

    universe = {}
    universe.update(data.get("stocks") or {})
    universe.update(data.get("core") or {})
    universe.update(data.get("index") or {})

    for symbol, px in universe.items():
        if not isinstance(px, dict) or "error" in px:
            continue
        situation = situations.get(symbol) or {}
        day = num(px.get("day_chg"))
        rsi = num(px.get("rsi"))
        drawdown = num(
            px.get("strategy_drawdown")
            if px.get("strategy_drawdown") is not None
            else px.get("window_drawdown")
        )
        stage = situation.get("stage") or ((data.get("trend_pulse") or {}).get(symbol) or {}).get("state") or ""
        priority = num(situation.get("research_priority"))
        previous_stage = prior.get(symbol)
        changed_stage = bool(previous_stage and stage and previous_stage != stage)
        conflicts = len(situation.get("contradictions") or [])

        level = "quiet"
        reasons = []
        timing = "无需处理"
        action_text = "自动记录，暂不打扰。"

        if day is not None and abs(day) >= 0.10:
            level = "action"
            reasons.append(f"单日涨跌 {day:+.1%}，达到重大异动阈值")
            timing = "今天"
            action_text = "今天优先研究异动来源、成交量与事件驱动；不在原因未确认时机械追涨或抄底。"
        elif day is not None and abs(day) >= 0.05:
            level = "review"
            reasons.append(f"单日涨跌 {day:+.1%}，达到重点复查阈值")
            timing = "今天"
            action_text = "今天完成一次专项复查，确认是个股事件、行业共振还是市场系统性波动。"

        if changed_stage:
            if LEVEL_RANK[level] < LEVEL_RANK["review"]:
                level = "review"
            reasons.append(f"Trend Pulse 阶段从 {previous_stage} 变为 {stage}")
            timing = "今天"
            action_text = "今天重新检查趋势结构与原有 Thesis，确认是否需要改变观察计划。"

        if priority is not None and priority >= 70:
            if LEVEL_RANK[level] < LEVEL_RANK["review"]:
                level = "review"
            reasons.append(f"V5.4 研究优先级 {priority:.0f}/100")
            timing = "今天"
            action_text = "今天列入重点研究队列，并核对支持证据与反证。"
        elif priority is not None and priority >= 58 and level == "quiet":
            level = "watch"
            reasons.append(f"V5.4 研究优先级 {priority:.0f}/100")
            timing = "明日复查"
            action_text = "进入观察列表，下一交易日重新检查是否出现新的确认信号。"

        if conflicts >= 2:
            if LEVEL_RANK[level] < LEVEL_RANK["review"]:
                level = "review"
            reasons.append(f"存在 {conflicts} 条相互矛盾证据")
            timing = "今天"
            action_text = "今天优先处理矛盾证据，避免只看支持当前观点的信息。"

        if rsi is not None and rsi >= 80 and day is not None and day > 0.03:
            if LEVEL_RANK[level] < LEVEL_RANK["review"]:
                level = "review"
            reasons.append(f"RSI {rsi:.0f} 且当日继续上涨")
            timing = "今天"
            action_text = "今天重点评估追高风险、事件持续性和回撤容忍度。"

        rows.append({
            "symbol": symbol,
            "level": level,
            "timing": timing,
            "action": action_text,
            "reasons": reasons,
            "day_change": day,
            "rsi": rsi,
            "drawdown": drawdown,
            "stage": stage,
            "previous_stage": previous_stage,
            "research_priority": priority,
            "contradictions": conflicts,
        })

    return sorted(
        rows,
        key=lambda row: (
            LEVEL_RANK[row["level"]],
            row.get("research_priority") or 0,
            abs(row.get("day_change") or 0),
        ),
        reverse=True,
    )


def build_discovery_queue(watch_rows: List[dict]) -> List[dict]:
    """V5.5 phase-1 anomaly discovery.

    This intentionally uses the currently covered market universe only.
    Full-market SEC/FDA/news discovery will attach to the same schema later.
    """
    queue = []
    for row in watch_rows:
        day = row.get("day_change")
        if day is None:
            continue
        if abs(day) >= 0.08:
            queue.append({
                "symbol": row["symbol"],
                "source": "covered-universe-anomaly",
                "event_strength": "high" if abs(day) >= 0.15 else "medium",
                "price_change": day,
                "stage": row.get("stage"),
                "research_priority": row.get("research_priority"),
                "next_step": "核对官方公司事件、新闻、成交量和行业联动；确认事件真实性后再决定是否升级。",
                "guardrail": "异常上涨本身不是买入信号。",
            })
    return queue[:12]


def build_attention_summary(rows: List[dict], discovery: List[dict]) -> dict:
    counts = {k: sum(1 for row in rows if row["level"] == k) for k in LEVEL_RANK}
    headline = "自主扫描完成：当前没有需要打扰你的重大变化。"
    if counts["action"]:
        headline = f"自主扫描发现 {counts['action']} 项需要今天处理的变化。"
    elif counts["review"]:
        headline = f"自主扫描发现 {counts['review']} 项需要今天复查的变化。"
    elif counts["watch"]:
        headline = f"自主扫描发现 {counts['watch']} 项进入观察队列。"

    return {
        "headline": headline,
        "counts": counts,
        "discovery_count": len(discovery),
        "top_attention": [row for row in rows if row["level"] != "quiet"][:10],
    }


def build_agent(data: dict, learning: dict, previous: dict) -> dict:
    watch = classify_watchlist(data, learning, previous)
    discovery = build_discovery_queue(watch)
    summary = build_attention_summary(watch, discovery)

    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": data.get("updated"),
        "mode": "autonomous-research-phase-1",
        "attention_summary": summary,
        "watchlist_attention": watch,
        "discovery_queue": discovery,
        "private_position_agent": {
            "mode": "browser-private",
            "reason": "真实期权持仓受 Supabase RLS 保护，不写入公开 docs/data.json。",
            "capabilities": [
                "扫描全部开放期权持仓",
                "读取 Alpaca 报价 / Delta / IV / DTE / Bid-Ask",
                "根据剩余收益、临期、价差与事件生成今天/明天/继续持有方案",
            ],
        },
        "guardrails": [
            "系统可以自主研究、排序和提示，但不会自动下单。",
            "任何高优先级异动都必须同时展示支持证据和反证。",
            "异常上涨或高研究优先级本身不是买入信号。",
            "真实持仓不得写入公开静态文件。",
        ],
        "roadmap": {
            "next": [
                "full-market SEC/FDA/news discovery",
                "company-event attribution",
                "options remaining-edge model",
                "agent audit/error memory",
            ]
        },
    }


def main() -> int:
    data = load(DASHBOARD)
    learning = load(LEARNING)
    previous = load(PREVIOUS)
    agent = build_agent(data, learning, previous)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(agent, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "version": agent["version"],
        "summary": agent["attention_summary"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
