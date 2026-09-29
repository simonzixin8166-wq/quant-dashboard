#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import List

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "docs" / "data.json"
HISTORY = ROOT / "docs" / "research" / "historical_journal.json"
MACRO = ROOT / "docs" / "research" / "macro_context.json"
OUT = ROOT / "docs" / "research" / "learning_engine.json"
VERSION = "5.4.0"

POSITIVE_STAGES = {"趋势启动", "二次启动", "趋势延续"}
NEGATIVE_STAGES = {"趋势退潮", "趋势恶化"}


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def stage_weight(stage):
    return {
        "二次启动": 15,
        "趋势启动": 12,
        "趋势延续": 8,
        "修复中": 3,
        "高位钝化": -3,
        "趋势退潮": -10,
        "趋势恶化": -18,
    }.get(stage, 0)


def technical_similarity(current: dict, event: dict) -> float:
    score = 0.0
    weight = 0.0

    if current.get("stage") and event.get("stage"):
        weight += 45
        if current["stage"] == event["stage"]:
            score += 45

    current_score = num(current.get("score"))
    event_score = num(event.get("score"))
    if current_score is not None and event_score is not None:
        weight += 30
        score += 30 * max(0.0, 1.0 - abs(current_score - event_score) / 100.0)

    if current.get("weekly") and event.get("weekly"):
        weight += 15
        if current["weekly"] == event["weekly"]:
            score += 15

    if current.get("zone") and event.get("zone"):
        weight += 10
        if current["zone"] == event["zone"]:
            score += 10

    return round(score / weight * 100.0, 1) if weight else 0.0


def similarity_summary(current: dict, events: List[dict], limit: int = 40) -> dict:
    ranked = sorted(
        (
            (technical_similarity(current, event), event)
            for event in events
            if event.get("symbol") != current.get("symbol")
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )[:limit]

    rows = []
    for similarity, event in ranked:
        if similarity < 55:
            continue
        outcome = (event.get("outcomes") or {}).get("60")
        rows.append(
            {
                "similarity": similarity,
                "symbol": event.get("symbol"),
                "date": event.get("date"),
                "stage": event.get("stage"),
                "return_60": num((outcome or {}).get("return")),
                "mae_60": num((outcome or {}).get("mae")),
            }
        )

    returns = [row["return_60"] for row in rows if row["return_60"] is not None]
    maes = [row["mae_60"] for row in rows if row["mae_60"] is not None]

    return {
        "method": "technical-v1-stage+pulse+weekly+zone",
        "n": len(returns),
        "median_return_60": median(returns) if returns else None,
        "positive_rate_60": (
            sum(1 for value in returns if value > 0) / len(returns)
            if returns
            else None
        ),
        "median_mae_60": median(maes) if maes else None,
        "matches": rows[:10],
    }


def contradictions(situation: dict, macro: dict, market: dict) -> List[dict]:
    output = []
    stage = situation.get("stage")
    rsi = num(situation.get("rsi"))
    macro_risk = num((macro.get("regime") or {}).get("macro_risk_score"))

    if stage in POSITIVE_STAGES and macro_risk is not None and macro_risk >= 65:
        output.append(
            {
                "type": "macro_vs_trend",
                "severity": "high",
                "message": "技术趋势偏强，但宏观风险分处于高位。",
            }
        )

    if stage in POSITIVE_STAGES and rsi is not None and rsi >= 75:
        output.append(
            {
                "type": "overbought",
                "severity": "medium",
                "message": "趋势偏强但 RSI 已进入高位区。",
            }
        )

    if stage in NEGATIVE_STAGES and situation.get("weekly") == "多头":
        output.append(
            {
                "type": "timeframe_conflict",
                "severity": "medium",
                "message": "日线转弱但周线仍偏多，多周期方向冲突。",
            }
        )

    divergence_level = ((market.get("divergence") or {}).get("level"))
    if stage in POSITIVE_STAGES and divergence_level in {"l2", "l3"}:
        output.append(
            {
                "type": "breadth_divergence",
                "severity": "medium",
                "message": "个股趋势偏强，但大盘宽度出现背离。",
            }
        )

    return output


def current_situations(data: dict, history: dict, macro: dict) -> List[dict]:
    pulses = data.get("trend_pulse") or {}
    profiles = history.get("profiles") or {}
    events = history.get("recent_events") or []
    market = data.get("market_regime") or {}
    output = []

    for symbol, pulse in pulses.items():
        if not isinstance(pulse, dict) or not pulse.get("available"):
            continue

        price_row = (
            (data.get("stocks") or {}).get(symbol)
            or (data.get("core") or {}).get(symbol)
            or (data.get("index") or {}).get(symbol)
            or {}
        )
        stage = pulse.get("state") or ""
        profile = profiles.get(stage) or {}
        evidence = profile.get("evidence") or {}
        horizon_60 = (profile.get("horizons") or {}).get("60") or {}

        situation = {
            "timestamp": pulse.get("date") or data.get("updated"),
            "symbol": symbol,
            "price": num(price_row.get("close")),
            "drawdown": num(
                price_row.get("strategy_drawdown")
                if price_row.get("strategy_drawdown") is not None
                else price_row.get("window_drawdown")
            ),
            "rsi": num(
                pulse.get("rsi")
                if pulse.get("rsi") is not None
                else price_row.get("rsi")
            ),
            "score": num(pulse.get("score")),
            "stage": stage,
            "weekly": pulse.get("weekly"),
            "zone": None,
            "structure": pulse.get("structure"),
            "supertrend": pulse.get("supertrend"),
            "data_confidence": pulse.get("confidence"),
            "macro": macro.get("regime") or {},
            "market_regime": market.get("tier_label"),
        }

        similarity = similarity_summary(situation, events)
        conflicts = contradictions(situation, macro, market)

        historical_adjustment = num(evidence.get("research_adjustment")) or 0
        macro_risk = num((macro.get("regime") or {}).get("macro_risk_score"))

        priority = (
            50
            + stage_weight(stage)
            + historical_adjustment
            + (5 if pulse.get("weekly") == "多头" else -5 if pulse.get("weekly") == "空头" else 0)
        )

        if macro_risk is not None:
            priority -= max(0.0, (macro_risk - 50.0) * 0.25)

        priority -= sum(6 if item["severity"] == "high" else 3 for item in conflicts)
        priority = max(0.0, min(100.0, round(priority, 1)))

        situation.update(
            {
                "historical_stage_evidence": {
                    "n60": horizon_60.get("n"),
                    "median60": horizon_60.get("median"),
                    "positive_rate60": horizon_60.get("positive_rate"),
                    "label": evidence.get("label"),
                },
                "similarity": similarity,
                "contradictions": conflicts,
                "research_priority": priority,
            }
        )
        output.append(situation)

    return sorted(output, key=lambda row: row["research_priority"], reverse=True)


def strategy_memory(history: dict) -> dict:
    output = {}
    for stage, profile in (history.get("profiles") or {}).items():
        output[stage] = {
            "evidence": profile.get("evidence") or {},
            "horizons": profile.get("horizons") or {},
            "learned_from": "STOOQ causal event study",
            "scope": "research-priority only",
        }
    return output


def build_engine(data: dict, history: dict, macro: dict) -> dict:
    situations = current_situations(data, history, macro)

    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": data.get("updated"),
        "architecture": [
            "market_context",
            "macro_regime",
            "situation_memory",
            "similarity_engine",
            "strategy_memory",
            "contradiction_engine",
            "opportunity_queue",
        ],
        "macro_context": macro.get("regime") or {"status": "unavailable"},
        "situation_memory": situations,
        "strategy_memory": strategy_memory(history),
        "opportunity_queue": [
            {
                "rank": index + 1,
                "symbol": situation["symbol"],
                "research_priority": situation["research_priority"],
                "stage": situation["stage"],
                "similarity_n60": situation["similarity"]["n"],
                "contradictions": len(situation["contradictions"]),
            }
            for index, situation in enumerate(situations[:12])
        ],
        "guardrails": [
            "Research priority is not an order instruction.",
            "Core QQQM/VGT/QLD thresholds are immutable here.",
            "No position size or automatic trade is produced.",
            "Macro replay must use point-in-time vintages.",
        ],
        "quality": {
            "history_available": bool(history),
            "macro_available": bool(macro),
            "situations": len(situations),
        },
    }


def main() -> int:
    engine = build_engine(load(DASHBOARD), load(HISTORY), load(MACRO))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(engine, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "version": engine["version"],
                "situations": engine["quality"]["situations"],
                "top": engine["opportunity_queue"][:3],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
