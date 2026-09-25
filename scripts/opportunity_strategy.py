"""Pure strategy calculations for the dashboard opportunity modules.

Rows are expected in the same shape used by fetch_and_build.py and may arrive
newest-first.  This module deliberately returns signals and percentages only;
it never turns a signal into dollars or contract quantities.
"""

from __future__ import annotations

import datetime as _dt
import math


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _ascending(rows):
    clean = []
    for row in rows or []:
        close = _number(row.get("close"))
        date = str(row.get("datetime") or row.get("date") or "")[:10]
        if close and date:
            clean.append({"date": date, "close": close})
    return sorted(clean, key=lambda row: row["date"])


def _sma(values, index, length):
    if index + 1 < length:
        return None
    window = values[index - length + 1:index + 1]
    return sum(window) / length


def _rsi(values, index, length=14):
    if index < length:
        return None
    gains, losses = [], []
    start = max(1, index - length + 1)
    for cursor in range(start, index + 1):
        change = values[cursor] - values[cursor - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = sum(gains) / length
    average_loss = sum(losses) / length
    if average_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + average_gain / average_loss)


def decide_tqqq_state(previous_target, snapshot):
    """Return the next 0/33/67 target with explicit rule precedence."""
    previous = previous_target if previous_target in (0, 33, 67) else 67
    if snapshot.get("hard_exit"):
        return 0, "hard_exit", "硬退出：目标降至0%"
    if snapshot.get("tier2"):
        return 0, "tier2", "二级降险：目标降至0%"
    if snapshot.get("tier1"):
        return min(previous, 33), "tier1", "一级降险：目标不高于33%"
    if snapshot.get("full_restore"):
        return 67, "full_restore", "趋势确认：恢复X2目标敞口"
    if snapshot.get("oversold_restore") or snapshot.get("trend_restore"):
        return max(previous, 33), "partial_restore", "恢复部分敞口至33%"
    return previous, "hold", "保持上一收盘目标"


def build_tqqq_x2_strategy(qqq_rows, vix_rows, recorded_position=0):
    qqq = _ascending(qqq_rows)
    vix_map = {row["date"]: row["close"] for row in _ascending(vix_rows)}
    qqq = [row for row in qqq if row["date"] in vix_map]
    if len(qqq) < 205:
        return {"available": False, "error": "QQQ/VIX完整日线不足205个共同交易日"}

    closes = [row["close"] for row in qqq]
    states = []
    previous_target = 67
    for index, row in enumerate(qqq):
        ma20 = _sma(closes, index, 20)
        ma50 = _sma(closes, index, 50)
        ma200 = _sma(closes, index, 200)
        rsi = _rsi(closes, index, 14)
        if None in (ma20, ma50, ma200, rsi) or index < 5:
            continue
        vix = vix_map[row["date"]]
        comparison_date = qqq[index - 3]["date"] if index >= 3 else ""
        old_vix = vix_map.get(comparison_date)
        vix_3d = vix / old_vix - 1.0 if old_vix else None
        previous_ma20 = _sma(closes, index - 5, 20)
        previous_day_ma20 = _sma(closes, index - 1, 20)
        previous_day_ma50 = _sma(closes, index - 1, 50)
        ma20_rising = bool(previous_ma20 and ma20 > previous_ma20)
        two_below_ma50 = bool(previous_day_ma50 and closes[index - 1] < previous_day_ma50 and row["close"] < ma50)
        two_above_ma20 = bool(previous_day_ma20 and closes[index - 1] > previous_day_ma20 and row["close"] > ma20)
        hard_exit = (vix > 26 and row["close"] < ma50) or (row["close"] < ma200 and vix > 24)
        tier2 = bool(vix_3d is not None and vix_3d > .20 and vix >= 20 and (row["close"] <= ma50 * .995 or two_below_ma50))
        tier1 = bool(vix_3d is not None and vix_3d > .20 and vix >= 18 and row["close"] < ma20)
        oversold_restore = bool(rsi <= 30 and not hard_exit and vix <= 26)
        trend_restore = bool(vix_3d is not None and two_above_ma20 and ma20_rising and vix_3d <= .20)
        full_restore = bool(trend_restore and row["close"] > ma50 and vix < 20)
        flags = {
            "hard_exit": hard_exit, "tier2": tier2, "tier1": tier1,
            "oversold_restore": oversold_restore, "trend_restore": trend_restore,
            "full_restore": full_restore,
        }
        target, rule, action = decide_tqqq_state(previous_target, flags)
        states.append({
            "date": row["date"], "qqq": row["close"], "ma20": ma20,
            "ma50": ma50, "ma200": ma200, "rsi14": rsi, "vix": vix,
            "vix_3d_change": vix_3d, "ma20_rising": ma20_rising,
            "target_position": target, "target_daily_exposure": target * 3 / 100,
            "rule": rule, "action": action, **flags,
        })
        previous_target = target

    if not states:
        return {"available": False, "error": "无法形成有效的X2策略状态"}
    current = states[-1]
    previous = states[-2] if len(states) > 1 else None
    changed = bool(previous and previous["target_position"] != current["target_position"])
    labels = {0: "防守 · 空仓", 33: "部分敞口", 67: "X2目标敞口"}
    return {
        "available": True,
        "strategy": "X2",
        "date": current["date"],
        "recorded_position": int(recorded_position or 0),
        "target_position": current["target_position"],
        "target_daily_exposure": current["target_daily_exposure"],
        "status_label": labels[current["target_position"]],
        "action": current["action"],
        "rule": current["rule"],
        "changed": changed,
        "snapshot": current,
        "history": states[-90:],
        "note": "收盘确认、次日执行；仅提供目标敞口，不计算金额或自动下单。",
    }


def build_leaps_radar(asset_rows, vix_value=None):
    results = []
    for symbol in ("QQQ", "SMH", "VGT"):
        rows = _ascending((asset_rows or {}).get(symbol) or [])
        if len(rows) < 205:
            results.append({"symbol": symbol, "available": False, "error": "完整日线不足205天"})
            continue
        closes = [row["close"] for row in rows]
        index = len(rows) - 1
        rsi = _rsi(closes, index, 14)
        previous_rsi = _rsi(closes, index - 1, 14)
        ma200 = _sma(closes, index, 200)
        prior_ma200 = _sma(closes, index - 20, 200) if index >= 219 else None
        high63 = max(closes[-63:])
        drawdown = closes[-1] / high63 - 1.0
        strong = bool(rsi is not None and previous_rsi is not None and rsi <= 30 and previous_rsi <= 30 and drawdown <= -.10)
        candidate = bool(rsi is not None and rsi <= 35 and drawdown <= -.08)
        watch = bool(rsi is not None and (rsi <= 40 or drawdown <= -.05))
        trend_risk = bool(ma200 and prior_ma200 and closes[-1] < ma200 and ma200 < prior_ma200)
        vix_risk = bool(_number(vix_value) and float(vix_value) >= 30)
        if strong:
            key, label, level = "strong", "强候选", "l3"
        elif candidate:
            key, label, level = "candidate", "候选", "l2"
        elif watch:
            key, label, level = "watch", "观察", "l1"
        else:
            key, label, level = "normal", "未触发", "l1"
        if key in ("strong", "candidate") and (trend_risk or vix_risk):
            label += " · 高风险"
        results.append({
            "symbol": symbol, "available": True, "date": rows[-1]["date"],
            "close": closes[-1], "rsi14": rsi, "previous_rsi14": previous_rsi,
            "high63": high63, "drawdown63": drawdown, "ma200": ma200,
            "dist_200ma": closes[-1] / ma200 - 1.0 if ma200 else None,
            "ma200_rising": bool(prior_ma200 and ma200 >= prior_ma200),
            "trend_risk": trend_risk, "vix_risk": vix_risk,
            "status": key, "status_label": label, "risk_level": level,
        })
    return {
        "date": max((row.get("date", "") for row in results), default=""),
        "vix": _number(vix_value), "assets": results,
        "growth_filter": {"dte_min": 365, "dte_max": 900, "delta_min": .50, "delta_max": .60},
        "replacement_filter": {"dte_min": 540, "dte_max": 900, "delta_min": .70, "delta_max": .85},
        "risk_limits": {"single_pct": .01, "total_pct": .03},
        "note": "只提示机会与合约筛选条件；不计算投入金额、合约数量或自动下单。",
    }


def merge_alert_history(previous, tqqq, leaps, limit=240):
    items = [dict(item) for item in (previous or []) if isinstance(item, dict)]
    if tqqq.get("available") and (tqqq.get("changed") or tqqq.get("target_position") != 67):
        items.append({
            "date": tqqq["date"], "kind": "TQQQ_X2", "symbol": "TQQQ",
            "level": "l3" if tqqq["target_position"] == 0 else "l2",
            "label": tqqq["action"], "value": tqqq["target_position"],
        })
    for row in leaps.get("assets", []):
        if row.get("status") in ("candidate", "strong"):
            items.append({
                "date": row["date"], "kind": "LEAPS", "symbol": row["symbol"],
                "level": row["risk_level"], "label": row["status_label"],
                "value": row.get("drawdown63"),
            })
    deduped = {}
    for item in items:
        key = (item.get("date"), item.get("kind"), item.get("symbol"))
        deduped[key] = item
    return sorted(deduped.values(), key=lambda row: (row.get("date", ""), row.get("kind", ""), row.get("symbol", "")), reverse=True)[:limit]
