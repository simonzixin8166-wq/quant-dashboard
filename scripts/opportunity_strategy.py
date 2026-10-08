"""Pure strategy calculations for the dashboard opportunity modules.

Rows are expected in the same shape used by fetch_and_build.py and may arrive
newest-first.  This module deliberately returns signals and percentages only;
it never turns a signal into dollars or contract quantities.
"""

from __future__ import annotations

import datetime as _dt
import math

try:
    from playbook_config import TQQQ_RULES, LEAPS_RULES, PLAYBOOKS
except ModuleNotFoundError:
    import os, sys
    sys.path.insert(0, os.path.dirname(__file__))
    from playbook_config import TQQQ_RULES, LEAPS_RULES, PLAYBOOKS


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
    targets=TQQQ_RULES["targets"]
    defensive,partial,x2=targets["defensive"],targets["partial"],targets["x2"]
    previous = previous_target if previous_target in (defensive, partial, x2) else x2
    if snapshot.get("hard_exit"):
        return defensive, "hard_exit", "硬退出：目标降至0%"
    if snapshot.get("tier2"):
        return defensive, "tier2", "二级降险：目标降至0%"
    if snapshot.get("tier1"):
        return min(previous, partial), "tier1", "一级降险：目标不高于33%"
    if snapshot.get("full_restore"):
        return x2, "full_restore", "趋势确认：恢复X2目标敞口"
    if snapshot.get("oversold_restore") or snapshot.get("trend_restore"):
        return max(previous, partial), "partial_restore", "恢复部分敞口至33%"
    return previous, "hold", "保持上一收盘目标"


def build_tqqq_x2_strategy(qqq_rows, vix_rows, recorded_position=0):
    qqq = _ascending(qqq_rows)
    vix_map = {row["date"]: row["close"] for row in _ascending(vix_rows)}
    qqq = [row for row in qqq if row["date"] in vix_map]
    if len(qqq) < 205:
        return {"available": False, "error": "QQQ/VIX完整日线不足205个共同交易日"}

    closes = [row["close"] for row in qqq]
    states = []
    previous_target = TQQQ_RULES["targets"]["x2"]
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
        hard=TQQQ_RULES["hard_exit"]
        hard_exit = (vix > hard["vix_ma50_gt"] and row["close"] < ma50) or (row["close"] < ma200 and vix > hard["vix_ma200_gt"])
        r2=TQQQ_RULES["tier2"]
        tier2 = bool(vix_3d is not None and vix_3d > r2["vix_3d_change_gt"] and vix >= r2["vix_min"] and (row["close"] <= ma50 * r2["ma50_buffer"] or two_below_ma50))
        r1=TQQQ_RULES["tier1"]
        tier1 = bool(vix_3d is not None and vix_3d > r1["vix_3d_change_gt"] and vix >= r1["vix_min"] and row["close"] < ma20)
        rr=TQQQ_RULES["oversold_restore"]
        oversold_restore = bool(rsi <= rr["rsi_lte"] and not hard_exit and vix <= rr["vix_lte"])
        tr=TQQQ_RULES["trend_restore"]
        trend_restore = bool(vix_3d is not None and two_above_ma20 and ma20_rising and vix_3d <= tr["vix_3d_change_lte"])
        fr=TQQQ_RULES["full_restore"]
        full_restore = bool(trend_restore and row["close"] > ma50 and vix < fr["vix_lt"])
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


PLAYBOOK_RISK_SINGLE=PLAYBOOKS["CP-03"]["risk_band_per_event"]["single_pct"]
PLAYBOOK_RISK_TOTAL=PLAYBOOKS["CP-03"]["exposure_cap_total"]

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
        strong_rule=LEAPS_RULES["strong"]
        strong = bool(rsi is not None and previous_rsi is not None and rsi <= strong_rule["rsi_two_sessions_lte"] and previous_rsi <= strong_rule["rsi_two_sessions_lte"] and drawdown <= strong_rule["drawdown63_lte"])
        candidate_rule=LEAPS_RULES["candidate"]
        candidate = bool(rsi is not None and rsi <= candidate_rule["rsi_lte"] and drawdown <= candidate_rule["drawdown63_lte"])
        watch_rule=LEAPS_RULES["watch"]
        watch = bool(rsi is not None and (rsi <= watch_rule["rsi_lte"] or drawdown <= watch_rule["drawdown63_lte"]))
        trend_risk = bool(ma200 and prior_ma200 and closes[-1] < ma200 and ma200 < prior_ma200)
        vix_risk = bool(_number(vix_value) and float(vix_value) >= LEAPS_RULES["risk_flags"]["vix_gte"])
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
        "growth_filter": dict(LEAPS_RULES["growth_filter"]),
        "replacement_filter": dict(LEAPS_RULES["replacement_filter"]),
        "risk_limits": {"single_pct": PLAYBOOK_RISK_SINGLE, "total_pct": PLAYBOOK_RISK_TOTAL},
        "note": "只提示机会与合约筛选条件；不计算投入金额、合约数量或自动下单。",
    }


def merge_alert_history(previous, tqqq, leaps, limit=None):
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
    rows=sorted(deduped.values(), key=lambda row: (row.get("date", ""), row.get("kind", ""), row.get("symbol", "")), reverse=True)
    return rows if limit is None else rows[:limit]


def build_leverage_rebound_signal(qqq_rows, vix_rows=None, tqqq_x2=None, leaps_radar=None, breadth=None):
    """Research-only TQQQ vs QQQ LEAPS rebound context.

    The source hypothesis is only activated after a material QQQ drawdown.
    It does not select a trade, size a position, or override TQQQ/LEAPS production rules.
    """
    qqq=_ascending(qqq_rows)
    if len(qqq)<205:
        return {"available":False,"error":"QQQ完整日线不足205天"}
    closes=[x["close"] for x in qqq]
    i=len(closes)-1
    high252=max(closes[-252:])
    drawdown=closes[-1]/high252-1.0 if high252 else None
    ma20=_sma(closes,i,20); ma50=_sma(closes,i,50); ma200=_sma(closes,i,200); rsi=_rsi(closes,i,14)
    prev_ma20=_sma(closes,i-5,20) if i>=5 else None
    ma20_rising=bool(ma20 and prev_ma20 and ma20>prev_ma20)
    vix_map={x["date"]:x["close"] for x in _ascending(vix_rows or [])}
    vix=vix_map.get(qqq[-1]["date"])
    if vix is None and vix_map:
        vix=list(vix_map.values())[-1]

    magnitude=abs(drawdown or 0)
    trigger_8=magnitude>=.08
    trigger_10=magnitude>=.10
    trigger_15=magnitude>=.15
    deep_bear=magnitude>=.20 or bool(ma200 and closes[-1]<ma200 and (vix or 0)>=24)
    repair=bool(ma20 and closes[-1]>ma20 and ma20_rising)
    strong_repair=bool(repair and ma50 and closes[-1]>ma50 and (vix is None or vix<22))
    volatile_sideways=bool(trigger_10 and ma20 and ma50 and closes[-1]<=max(ma20,ma50) and not deep_bear)
    breadth=breadth or {}
    b20=_number(breadth.get("b20")); b50=_number(breadth.get("b50")); slope=_number(breadth.get("slope_10d"))
    breadth_repair=bool(b20 is not None and b50 is not None and slope is not None and b20>=.40 and b50>=.40 and slope>0)
    breadth_fragile=bool((b20 is not None and b20<.30) or (b50 is not None and b50<.30))

    if not trigger_8:
        status,label,priority="inactive","未到回调研究区",30
    elif deep_bear:
        status,label,priority="risk","深熊/二次下探风险优先",92
    elif trigger_15 and strong_repair:
        status,label,priority="candidate","深回调后修复确认 · TQQQ/LEAPS对比",88
    elif trigger_10 and strong_repair:
        status,label,priority="candidate","10%+回调后修复确认 · TQQQ/LEAPS对比",84
    elif trigger_10 and volatile_sideways:
        status,label,priority="watch","10%+回调但仍震荡 · 等待形态选择",78
    else:
        status,label,priority="watch","接近/进入回调研究区",68

    support=[]; counter=[]; unknowns=[]
    support.append(f"QQQ距近252日高点 {drawdown:+.1%}" if drawdown is not None else "QQQ回撤待确认")
    if repair: support.append("QQQ已重新站上上行MA20，出现初步修复")
    if strong_repair: support.append("QQQ同时站上MA50且VIX未处高压区，修复确认更完整")
    if breadth_repair: support.append("市场宽度同步修复，反弹并非仅少数权重股推动")
    if tqqq_x2 and tqqq_x2.get("available"):
        support.append(f"TQQQ X2现有正式规则：{tqqq_x2.get('status_label')} / {tqqq_x2.get('action')}")
    qqq_leaps=next((x for x in ((leaps_radar or {}).get("assets") or []) if x.get("symbol")=="QQQ"),None)
    if qqq_leaps and qqq_leaps.get("available"):
        support.append(f"QQQ LEAPS Radar：{qqq_leaps.get('status_label')}")

    if breadth_fragile: counter.append("市场宽度仍脆弱，指数修复可能缺乏广度确认")
    if volatile_sideways: counter.append("价格仍位于MA20/MA50附近震荡，TQQQ存在波动率拖累，LEAPS也承受Theta/IV回落")
    if deep_bear: counter.append("回调已进入深熊/二次下探区，优先控制总杠杆而不是比较哪种工具收益更高")
    if vix is not None and vix>=28: counter.append(f"VIX={vix:.1f}，LEAPS可能含较高恐慌IV溢价")
    if trigger_10 and not repair: counter.append("QQQ尚未形成MA20修复确认，不把单纯跌幅视作进场条件")

    if vix is None: unknowns.append("VIX完整收盘数据缺失")
    if b20 is None or b50 is None: unknowns.append("市场宽度数据不完整")
    unknowns.append("LEAPS具体IV、Bid/Ask、期限结构需在期权链中单独核验")
    unknowns.append("博主关于不同情境下相对收益的判断属于待验证Source Hypothesis，需用MyAlpha历史样本继续验证")

    if status=="risk":
        prompt="优先确认是否仍在深熊扩散；TQQQ正式降险规则优先，LEAPS仅做有限风险研究，不因跌幅加杠杆。"
    elif status=="candidate":
        prompt="已进入TQQQ vs QQQ LEAPS比较窗口：结合修复速度、IV、宽度与TQQQ正式X2状态做情境研究。"
    elif status=="watch":
        prompt="进入回调观察区，但尚不足以选择工具；继续观察MA20/50、VIX与市场宽度。"
    else:
        prompt="当前QQQ未进入约8%–15%回调研究区，不提示新增TQQQ/LEAPS反弹策略。"

    return {
      "available":True,"version":"6.8.2","date":qqq[-1]["date"],"status":status,"label":label,"priority":priority,
      "qqq_close":closes[-1],"high252":high252,"drawdown252":drawdown,"rsi14":rsi,
      "ma20":ma20,"ma50":ma50,"ma200":ma200,"ma20_rising":ma20_rising,"vix":vix,
      "trigger_8":trigger_8,"trigger_10":trigger_10,"trigger_15":trigger_15,"deep_bear":deep_bear,
      "repair":repair,"strong_repair":strong_repair,"volatile_sideways":volatile_sideways,
      "breadth_repair":breadth_repair,"breadth_fragile":breadth_fragile,
      "supporting_evidence":support,"counter_evidence":counter,"unknowns":unknowns,
      "prompt":prompt,
      "source_method":{
        "author":"lionhill / 狮山巡礼","title":"市场大调整时：TQQQ还是QQQ LEAPS","url":"https://blog.wenxuecity.com/myblog/82610/202610/1012.html",
        "hypothesis":"QQQ约10%–15%回调后，根据反弹速度、震荡时间、IV与二次下探风险比较TQQQ和QQQ LEAPS；不作为生产交易规则。"
      },
      "guardrail":"研究提示层：不修改TQQQ X2、LEAPS单次1%/总3%等现有规则，不计算下单数量，不自动交易。"
    }
