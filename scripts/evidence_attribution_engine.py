#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "docs" / "data.json"
LEARNING = ROOT / "docs" / "research" / "learning_engine.json"
AUTONOMOUS = ROOT / "docs" / "research" / "autonomous_agent.json"
HISTORY = ROOT / "docs" / "research" / "historical_journal.json"
OUT = ROOT / "docs" / "research" / "evidence_attribution.json"
VERSION = "5.7.0"

POSITIVE = {"趋势启动", "二次启动", "趋势延续"}
CAUTION = {"高位钝化", "趋势退潮"}
NEGATIVE = {"趋势恶化"}
REPAIR = {"修复中", "震荡观察"}

GLOSSARY = {
    "Thesis": {
        "cn": "投资逻辑",
        "plain": "你为什么愿意研究或持有这家公司，以及哪些事实一旦改变就说明原来的理由可能失效。",
        "why": "没有投资逻辑，股价波动时就很难区分正常回撤和真正看错。"
    },
    "Breadcrumb": {
        "cn": "早期线索",
        "plain": "重大行情或事件发生前，逐步出现但单独看并不足以下结论的小证据。",
        "why": "多个独立线索持续累积，比单条新闻更有研究价值；但仍需要后续确认。"
    },
    "Early Bull Transition": {
        "cn": "早期多头转换",
        "plain": "短周期已经明显转强，但更高周期或价格确认还没有完全跟上。",
        "why": "它代表值得观察的早期阶段，不等于已经进入稳定主升趋势。"
    },
    "Confirmation Pending": {
        "cn": "等待确认",
        "plain": "已经出现改善信号，但还需要连续收盘、关键价位或更高周期共同验证。",
        "why": "避免只因为一天反弹或一次突破就过早把状态升级。"
    },
    "Confirmed Trend": {
        "cn": "趋势已确认",
        "plain": "价格结构、动量和较高周期大体同向，趋势证据比早期转换阶段更完整。",
        "why": "确认提高趋势可信度，但仍不代表没有回撤风险。"
    },
    "False Break": {
        "cn": "假突破 / 突破失败",
        "plain": "价格或趋势指标刚转强，随后很快跌回关键区域，原来的突破没有得到持续确认。",
        "why": "它提醒投资者重新检查原来的判断，而不是把第一次突破当成永久有效。"
    },
    "Weakening": {
        "cn": "趋势转弱",
        "plain": "原有上升结构还没有完全破坏，但动量、均线或多周期一致性正在变差。",
        "why": "通常先进入复查阶段，而不是机械等到完全破位才关注。"
    },
    "Breakdown": {
        "cn": "结构破坏",
        "plain": "趋势和价格结构已经明显恶化，原来的多头假设需要重新验证。",
        "why": "这不是自动卖出指令，而是要求重新检查投资逻辑、估值和风险暴露。"
    },
    "Expected Move": {
        "cn": "市场隐含预期波动",
        "plain": "期权价格反映的市场对某个时间窗口内大致可能波动幅度的估计。",
        "why": "财报期权策略中，Strike 离预期波动区间多远，往往比机械选择 ATM 更重要。"
    },
    "Failure Attribution": {
        "cn": "失败归因",
        "plain": "结果出来以后，把错误拆成趋势判断、时间周期、事件、估值、策略结构或参数等不同来源。",
        "why": "只有知道到底哪一部分错了，系统才应该调整对应权重，而不是整套策略一起改。"
    },
    "Research Priority": {
        "cn": "研究优先级",
        "plain": "系统决定先研究谁、先提醒谁的排序分数，不是买卖评分。",
        "why": "高分只代表值得优先检查，不代表应该买入。"
    },
}


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def prior_map(agent: dict) -> dict:
    return {
        row.get("symbol"): row
        for row in (agent.get("watchlist_attention") or [])
        if row.get("symbol")
    }


def trend_state(situation: dict, previous: dict | None = None) -> dict:
    stage = str(situation.get("stage") or "")
    weekly = str(situation.get("weekly") or "")
    conflicts = situation.get("contradictions") or []
    previous_stage = str((previous or {}).get("previous_stage") or "")

    state = "Confirmation Pending"
    cn = "等待确认"
    explanation = "当前信号尚不足以定义稳定趋势，需要继续观察价格结构与多周期确认。"
    invalidation = "若价格和趋势指标重新转弱，则继续保持观察或降级。"

    if previous_stage in POSITIVE and stage in NEGATIVE | REPAIR:
        state, cn = "False Break", "假突破 / 突破失败"
        explanation = "此前出现过转强阶段，但当前已经快速回落到修复或恶化状态，第一次突破没有持续确认。"
        invalidation = "只有重新站回关键趋势结构并获得更高周期确认，才考虑再次升级。"
    elif stage == "趋势启动":
        state, cn = "Early Bull Transition", "早期多头转换"
        explanation = "短周期已经出现由弱转强，但趋势刚开始，仍需要更高周期和后续收盘确认。"
        invalidation = "若趋势分数重新显著转弱、关键结构失守或周线继续背离，则早期转换失败。"
    elif stage == "二次启动":
        if weekly == "多头":
            state, cn = "Confirmed Trend", "趋势已确认"
            explanation = "趋势重新启动且周线同向，属于比首次启动更完整的多周期确认。"
            invalidation = "若重新跌回修复/恶化状态或周线转弱，则确认失效。"
        else:
            state, cn = "Confirmation Pending", "等待确认"
            explanation = "日线出现二次启动，但周线尚未同向，先等待多周期确认。"
            invalidation = "若日线再次回落，则视为二次启动未完成确认。"
    elif stage == "趋势延续":
        state, cn = "Confirmed Trend", "趋势已确认"
        explanation = "当前处于趋势延续阶段，结构和动量仍支持原方向。"
        invalidation = "若进入趋势退潮或恶化，需要重新评估趋势持续性。"
    elif stage == "高位钝化":
        state, cn = "Trend Mature", "趋势成熟 / 高位钝化"
        explanation = "趋势仍可能保持强势，但已经处于高位成熟阶段，新增追涨优势下降。"
        invalidation = "若高位整理后重新二次启动可恢复积极状态；若转为退潮则进入风险复查。"
    elif stage == "趋势退潮":
        state, cn = "Weakening", "趋势转弱"
        explanation = "原趋势仍有历史惯性，但当前动量和结构正在退潮，需要减少对旧趋势的依赖。"
        invalidation = "重新二次启动可恢复确认；进一步恶化则视为结构破坏。"
    elif stage == "趋势恶化":
        state, cn = "Breakdown", "结构破坏"
        explanation = "趋势结构已经明显恶化，原来的多头假设必须重新验证。"
        invalidation = "只有进入修复并完成新的确认流程，才考虑重新升级。"
    elif stage in REPAIR:
        state, cn = "Confirmation Pending", "等待确认"
        explanation = "当前属于修复或震荡阶段，已有改善但尚未形成稳定趋势。"
        invalidation = "若修复失败并重新恶化，则继续防守；若启动并获得确认，则升级。"

    if len(conflicts) >= 2 and state == "Confirmed Trend":
        state, cn = "Confirmation Pending", "等待确认"
        explanation += " 但当前存在多条相互矛盾证据，因此暂不视为完全确认。"

    return {
        "state": state,
        "label_cn": cn,
        "source_stage": stage,
        "weekly": weekly,
        "explanation": explanation,
        "invalidation": invalidation,
        "term_help": GLOSSARY.get(state) or {
            "cn": cn,
            "plain": explanation,
            "why": "用于把复杂趋势指标转换成可执行的研究阶段。"
        },
    }


def technical_breadcrumbs(situation: dict, previous: dict | None, discovery: dict | None) -> list[dict]:
    crumbs = []
    stage = situation.get("stage")
    weekly = situation.get("weekly")
    score = num(situation.get("score"))
    priority = num(situation.get("research_priority"))
    conflicts = situation.get("contradictions") or []

    if stage:
        crumbs.append({
            "type": "trend_state",
            "strength": "medium",
            "evidence": f"Trend Pulse 当前阶段：{stage}",
            "meaning": "说明当前技术结构处于什么阶段；它是研究线索，不是单独买卖信号。",
        })
    if weekly and weekly != "数据不足":
        crumbs.append({
            "type": "timeframe",
            "strength": "high" if weekly == "多头" and stage in POSITIVE else "medium",
            "evidence": f"周线方向：{weekly}",
            "meaning": "用更高周期检查日线信号是否得到确认，减少一次性反弹造成的误判。",
        })
    if score is not None and abs(score) >= 60:
        crumbs.append({
            "type": "momentum",
            "strength": "medium",
            "evidence": f"Trend Pulse 分数 {score:.0f}",
            "meaning": "分数绝对值较高表示趋势证据较集中，但高分不等于未来一定继续上涨或下跌。",
        })
    if previous and previous.get("previous_stage") and previous.get("previous_stage") != stage:
        crumbs.append({
            "type": "transition",
            "strength": "high",
            "evidence": f"阶段从 {previous.get('previous_stage')} 变化为 {stage}",
            "meaning": "状态变化通常比重复的同状态提醒更值得复查。",
        })
    if conflicts:
        crumbs.append({
            "type": "contradiction",
            "strength": "high" if len(conflicts) >= 2 else "medium",
            "evidence": f"存在 {len(conflicts)} 条反证或多周期冲突",
            "meaning": "系统主动保留反证，避免只收集支持当前观点的信息。",
        })
    if discovery:
        day = num(discovery.get("price_change"))
        crumbs.append({
            "type": "market_anomaly",
            "strength": discovery.get("event_strength") or "medium",
            "evidence": f"覆盖池出现异常波动{f' {day:+.1%}' if day is not None else ''}",
            "meaning": "异常波动只触发原因调查；在事件来源确认前不能当成追涨或抄底理由。",
        })
    if priority is not None and priority >= 70:
        crumbs.append({
            "type": "research_priority",
            "strength": "medium",
            "evidence": f"研究优先级 {priority:.0f}/100",
            "meaning": "代表应优先花时间研究，不是买入概率或收益率预测。",
        })
    return crumbs[:8]


def build_breadcrumb_engine(learning: dict, agent: dict) -> list[dict]:
    previous = prior_map(agent)
    discovery_map = {
        row.get("symbol"): row
        for row in (agent.get("discovery_queue") or [])
        if row.get("symbol")
    }
    rows = []
    for situation in (learning.get("situation_memory") or []):
        symbol = situation.get("symbol")
        if not symbol:
            continue
        prev = previous.get(symbol)
        trend = trend_state(situation, prev)
        crumbs = technical_breadcrumbs(situation, prev, discovery_map.get(symbol))
        high = sum(1 for x in crumbs if x["strength"] == "high")
        medium = sum(1 for x in crumbs if x["strength"] == "medium")
        score = min(100, high * 22 + medium * 10 + max(0, (num(situation.get("research_priority")) or 0) - 50) * 0.4)
        rows.append({
            "symbol": symbol,
            "evidence_score": round(score, 1),
            "status": "evidence-accumulating" if score >= 45 else "monitor",
            "trend_state": trend,
            "breadcrumbs": crumbs,
            "next_confirmation": trend["invalidation"],
            "source_scope": "当前仅使用已验证的行情、Trend Pulse、历史学习与覆盖池异动；尚未把论坛/SEC/FDA/公司新闻自动写入此评分。",
        })
    return sorted(rows, key=lambda x: x["evidence_score"], reverse=True)


def mature_outcome(event: dict, horizon: str = "20"):
    outcome = (event.get("outcomes") or {}).get(horizon)
    return num((outcome or {}).get("return")), num((outcome or {}).get("mae")), num((outcome or {}).get("mfe"))


def attribution_for_event(event: dict) -> dict | None:
    ret, mae, mfe = mature_outcome(event, "20")
    if ret is None:
        return None
    stage = str(event.get("stage") or "")
    weekly = str(event.get("weekly") or "")
    score = num(event.get("score"))
    tags = []
    hypothesis = []
    severity = "normal"

    if stage in POSITIVE and ret <= -0.08:
        tags.append("trend_false_positive")
        hypothesis.append("当时趋势状态偏多，但20个交易日结果明显为负：优先检查趋势确认是否过早。")
        severity = "review"
    if stage in POSITIVE and weekly not in {"多头", ""} and ret <= 0:
        tags.append("timeframe_confirmation_missing")
        hypothesis.append("日线偏强而周线未确认，多周期冲突可能是误判来源之一。")
        severity = "review"
    if stage in NEGATIVE | CAUTION and ret >= 0.12:
        tags.append("missed_upside")
        hypothesis.append("当时状态偏谨慎，但随后20日明显上涨：检查是否漏掉二次启动或修复后的确认。")
        severity = "review"
    if mae is not None and mae <= -0.12:
        tags.append("large_adverse_move")
        hypothesis.append("入档后经历较大不利波动，风险识别和无效条件应被单独复盘。")
        severity = "review"
    if not tags:
        tags.append("no_material_failure")
        hypothesis.append("当前20日结果没有触发明确失败归因阈值，保留样本但不调整学习权重。")

    return {
        "symbol": event.get("symbol"),
        "date": event.get("date"),
        "source_stage": stage,
        "weekly": weekly,
        "score": score,
        "return_20": ret,
        "mae_20": mae,
        "mfe_20": mfe,
        "severity": severity,
        "tags": tags,
        "attribution_hypotheses": hypothesis,
        "guardrail": "这是可检验的归因假设，不是已经证明的因果关系；只有重复成熟样本才允许影响 Learning Policy。",
    }


def failure_attribution(history: dict) -> dict:
    rows = []
    for event in history.get("recent_events") or []:
        item = attribution_for_event(event)
        if item:
            rows.append(item)
    review = [x for x in rows if x["severity"] == "review"]
    counts = {}
    for row in review:
        for tag in row["tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    return {
        "mature_samples_scanned": len(rows),
        "review_samples": len(review),
        "tag_counts": counts,
        "recent": review[:20],
        "method": "20-session outcome attribution hypotheses; no causal claim",
    }


def build(data: dict, learning: dict, agent: dict, history: dict) -> dict:
    breadcrumbs = build_breadcrumb_engine(learning, agent)
    failures = failure_attribution(history)
    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": data.get("updated"),
        "architecture": [
            "plain_language_glossary",
            "trend_state_machine",
            "breadcrumb_engine",
            "failure_attribution",
            "learning_policy_feedback",
        ],
        "glossary": GLOSSARY,
        "trend_state_machine": {
            "states": [
                "Early Bull Transition",
                "Confirmation Pending",
                "Confirmed Trend",
                "Trend Mature",
                "Weakening",
                "False Break",
                "Breakdown",
            ],
            "principle": "状态升级必须有后续确认；第一次转强不是自动买入信号。",
        },
        "breadcrumb_engine": {
            "method": "evidence accumulation v1",
            "top": breadcrumbs[:12],
            "coverage": len(breadcrumbs),
            "external_event_feed_status": "not-yet-connected",
            "note": "V5.7 首版只用已有可验证数据形成技术/市场 Breadcrumb；不会假装已经抓取到 SEC/FDA/论坛等外部事实。",
        },
        "failure_attribution": failures,
        "guardrails": [
            "Evidence Score 是研究优先级线索，不是买入概率。",
            "Failure Attribution 是归因假设，不是因果证明。",
            "任何自主学习只允许调整研究排序与提醒权重。",
            "QQQM/VGT/QLD 核心阈值不由本引擎修改。",
            "系统不会自动下单或修改持仓。",
            "真实期权持仓不得写入公开静态 JSON。",
        ],
    }


def main() -> int:
    result = build(load(DASHBOARD), load(LEARNING), load(AUTONOMOUS), load(HISTORY))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "version": result["version"],
        "breadcrumbs": result["breadcrumb_engine"]["coverage"],
        "attribution_review": result["failure_attribution"]["review_samples"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
