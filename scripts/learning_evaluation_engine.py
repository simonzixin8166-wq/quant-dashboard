#!/usr/bin/env python3
"""MyAlpha View V6.9 Learning Evaluation Engine.

Turns learning activity into an auditable scorecard:
- what the system has actually learned,
- what is still unproven,
- recurring evidence gaps and error patterns,
- method validation maturity,
- next learning priorities.

It never mutates production trading rules or places orders.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs/research"
PATHS = {
    "execution": RESEARCH / "research_execution.json",
    "planner": RESEARCH / "research_planner.json",
    "learning": RESEARCH / "learning_engine.json",
    "method": RESEARCH / "method_memory.json",
    "evidence": RESEARCH / "evidence_attribution.json",
    "history": RESEARCH / "historical_journal.json",
    "self_improvement": RESEARCH / "self_improvement.json",
}
OUT = RESEARCH / "learning_evaluation.json"

def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def pct(n, d):
    return round(n / d, 4) if d else 0.0

def classify_gap(text: str) -> str:
    t = str(text or "").lower()
    if any(k in t for k in ("ir官网", "官方证据", "sec", "新闻稿", "reuters", "ap/", "高优先级事件源")):
        return "官方/一手证据"
    if any(k in t for k in ("同业", "peer", "行业")):
        return "行业/同业证据"
    if any(k in t for k in ("move", "erp", "利率", "信用", "宏观")):
        return "宏观/跨资产数据"
    if any(k in t for k in ("5 日成熟", "20 日成熟", "60 日成熟", "120", "历史")):
        return "前瞻成熟样本"
    if any(k in t for k in ("期权", "iv", "delta", "p&l", "greek")):
        return "期权/私有结果"
    return "其他待验证项"

def method_rows(method: dict) -> list[dict]:
    rows = []
    for m in method.get("methods") or []:
        perf = m.get("performance") or {}
        horizons = {}
        for h in ("5", "20", "60", "120"):
            x = perf.get(h) or {}
            if x:
                horizons[h] = {
                    "n": x.get("n"),
                    "alignment_rate": x.get("alignment_rate"),
                    "avg_return": x.get("avg_return"),
                    "median_return": x.get("median_return"),
                }
        direct = int(m.get("direct_validated_events") or 0)
        if direct >= 20:
            maturity = "validated"
        elif direct >= 8:
            maturity = "developing"
        elif direct > 0:
            maturity = "early"
        else:
            maturity = "unproven"
        rows.append({
            "method": m.get("method"),
            "direct_validated_events": direct,
            "maturity": maturity,
            "horizons": horizons,
        })
    return rows

def historical_summary(history: dict) -> dict:
    s = history.get("summary") or {}
    return {
        "symbols": s.get("symbols", 0),
        "events": s.get("events", 0),
        "mature_20": s.get("mature_20", 0),
        "mature_60": s.get("mature_60", 0),
        "mature_120": s.get("mature_120", 0),
        "role": "历史库提供先验与相似情境；实时前瞻结果用于验证系统当时判断是否可靠。",
    }

def build(execution, planner, learning, method, evidence, history, self_improvement):
    results = execution.get("results") or []
    analyzed = len(results)
    high = sum(x.get("confidence") == "high" for x in results)
    medium = sum(x.get("confidence") == "medium" for x in results)
    low = sum(x.get("confidence") == "low" for x in results)
    with_counter = sum(bool(x.get("counter_evidence")) for x in results)
    with_unknowns = sum(bool(x.get("unknowns")) for x in results)

    all_unknowns = [u for x in results for u in (x.get("unknowns") or [])]
    gap_counts = Counter(classify_gap(u) for u in all_unknowns)
    gap_examples = {}
    for u in all_unknowns:
        k = classify_gap(u)
        gap_examples.setdefault(k, [])
        if len(gap_examples[k]) < 3 and u not in gap_examples[k]:
            gap_examples[k].append(u)

    gaps = [
        {"category": k, "count": n, "examples": gap_examples.get(k, [])}
        for k, n in gap_counts.most_common()
    ]

    fail = evidence.get("failure_attribution") or {}
    reviews = fail.get("external_outcome_reviews") or []
    error_tags = Counter()
    for row in reviews:
        for key in ("failure_tags", "tags", "labels"):
            vals = row.get(key) or []
            if isinstance(vals, str):
                vals = [vals]
            for v in vals:
                error_tags[str(v)] += 1
        for key in ("reason", "failure_reason", "attribution"):
            val = row.get(key)
            if isinstance(val, str) and val:
                error_tags[val] += 1

    methods = method_rows(method)
    method_counts = method.get("counts") or {}
    direct_methods = sum(x["direct_validated_events"] > 0 for x in methods)
    validated_methods = sum(x["maturity"] == "validated" for x in methods)

    history_summary = historical_summary(history)
    situation_count = ((learning.get("quality") or {}).get("situations")
                       or len(learning.get("situation_memory") or []))
    open_tasks = (planner.get("counts") or {}).get("open", 0)
    high_priority = (planner.get("counts") or {}).get("high_priority", 0)

    # Learning-health score is an engineering coverage score, not an investment score.
    components = {
        "research_execution": min(25, analyzed * 3),
        "counter_evidence_discipline": round(20 * pct(with_counter, analyzed), 1),
        "explicit_unknowns": round(15 * pct(with_unknowns, analyzed), 1),
        "historical_memory": 20 if history_summary["mature_60"] else 0,
        "direct_method_validation": min(20, direct_methods * 4),
    }
    health_score = round(sum(components.values()), 1)

    lessons = []
    if analyzed:
        lessons.append(f"本轮自动完成 {analyzed} 项研究，其中高置信度 {high} 项；所有结论继续区分支持证据、反证和未知项。")
    if history_summary["mature_60"]:
        lessons.append(f"历史库已有 {history_summary['mature_60']} 个60日成熟状态样本，可用于相似情境先验；实时前瞻样本仍单独验证。")
    if method_counts.get("source_records"):
        lessons.append(f"Method Memory 已吸收 {method_counts.get('source_records')} 条来源记录，但直接方法验证仍需继续积累。")
    if gaps:
        lessons.append(f"当前最大证据缺口是“{gaps[0]['category']}”（{gaps[0]['count']} 项），下一轮研究应优先补齐而不是猜测。")
    if not direct_methods:
        lessons.append("当前外部方法仍没有足够直接归因样本，因此不能把博主观点晋级为正式策略。")

    next_focus = []
    for g in gaps[:3]:
        next_focus.append({
            "priority": len(next_focus) + 1,
            "focus": g["category"],
            "reason": f"本轮出现 {g['count']} 个未完成验证项。",
            "action": "优先补证据并记录结果；不得用推测填补缺失事实。",
        })
    if not direct_methods:
        next_focus.append({
            "priority": len(next_focus) + 1,
            "focus": "方法直接验证",
            "reason": "当前方法库以来源记录和候选事件为主，直接方法归因样本不足。",
            "action": "继续锁定触发时点并等待5/20/60/120日结果成熟。",
        })

    return {
        "version": "6.9.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": "Learning Evaluation · 自我评估中心",
        "learning_health": {
            "score": health_score,
            "max_score": 100,
            "meaning": "衡量学习链覆盖、反证纪律、未知项透明度、历史记忆和直接方法验证成熟度；不是收益率或买卖评分。",
            "components": components,
        },
        "research_scorecard": {
            "analyzed": analyzed,
            "high_confidence": high,
            "medium_confidence": medium,
            "low_confidence": low,
            "with_counter_evidence": with_counter,
            "with_unknowns": with_unknowns,
            "open_tasks": open_tasks,
            "high_priority_tasks": high_priority,
            "situation_memory": situation_count,
        },
        "outcome_memory": history_summary,
        "method_validation": {
            "source_records": method_counts.get("source_records", 0),
            "eligible_triggered_events": method_counts.get("eligible_triggered_events", 0),
            "direct_method_links": method_counts.get("direct_method_links", 0),
            "mature60_eligible_events": method_counts.get("mature60_eligible_events", 0),
            "methods_with_direct_validation": direct_methods,
            "validated_methods": validated_methods,
            "methods": methods,
        },
        "evidence_gaps": gaps,
        "error_memory": {
            "review_samples": len(reviews),
            "top_patterns": [{"pattern": k, "count": n} for k, n in error_tags.most_common(8)],
            "principle": "错误记忆只用于定位研究流程问题；不因单一样本自动修改交易规则。",
        },
        "lessons": lessons,
        "next_learning_focus": next_focus,
        "shadow_status": {
            "candidate_count": (self_improvement.get("candidate_brain") or {}).get("count", 0),
            "eligible_for_review": len((self_improvement.get("shadow_brain") or {}).get("eligible_for_review") or []),
            "production_brain": (self_improvement.get("production_brain") or {}).get("mode", "locked"),
        },
        "guardrails": [
            "自我评估只评价研究与学习质量，不评价投资者本人。",
            "学习健康分不是收益预测、胜率或买卖分数。",
            "未成熟前瞻样本不得提前算作验证成功。",
            "博客与外部观点必须经过独立历史/前瞻验证后才可提高研究权重。",
            "仓位、下单、核心配置和Hard Exit阈值继续锁定，必须人工决定。",
        ],
    }

def main():
    out = build(
        load(PATHS["execution"]),
        load(PATHS["planner"]),
        load(PATHS["learning"]),
        load(PATHS["method"]),
        load(PATHS["evidence"]),
        load(PATHS["history"]),
        load(PATHS["self_improvement"]),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "version": out["version"],
        "learning_health": out["learning_health"]["score"],
        "evidence_gaps": len(out["evidence_gaps"]),
        "methods_with_direct_validation": out["method_validation"]["methods_with_direct_validation"],
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
