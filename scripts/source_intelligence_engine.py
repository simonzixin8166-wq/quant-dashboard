#!/usr/bin/env python3
"""External source intelligence -> MyAlpha research-learning layer.

The engine preserves provenance and separates:
1) what an external author said/did;
2) MyAlpha's own validation state;
3) whether the item is only a research alert or has matured into a learning sample.

It never changes core trading thresholds and never issues automatic orders.
"""
from __future__ import annotations
import json, os, re, urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "source_intelligence.json"
ARCHIVES = [ROOT / "docs" / "data" / f"brightline_2026_q{i}.json" for i in (1,2,3)]
FULLTEXT_INSIGHTS = ROOT / "docs" / "data" / "brightline_2026_fulltext_insights.json"
FEED_URL = os.getenv(
    "WXC_RESEARCH_FEED_URL",
    "https://raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/research_feed.json",
)

SYMBOLS = {
    "INTC","IREN","TSLA","QQQ","QQQM","VGT","QLD","TQQQ","NVDA","MU","AMZN",
    "NOW","META","SMH","SPY","VOO","ORCL","IBIT","BTC","COIN","NBIS","CRWV","SNDK",
    "PYPL","GOOG","GOOGL","AAPL","MSFT","JPM","AMAT","LITE","BE","MRVL","RSP","QCOM",
}
# Uppercase tokens from forum titles are useful ticker candidates, but a conservative
# blocklist prevents common English abbreviations from becoming symbols.
TICKER_BLOCKLIST = {
    "AI","CEO","CFO","CTO","COO","SEC","FED","FOMC","CPI","PPI","GDP","EPS","PE",
    "DCF","ATH","ATL","LOL","IMO","IMHO","FYI","MM","SP","CC","DTE","IV","OI","RSI",
    "MA","USD","US","ETF","ETFS","THE","AND","BUT","FOR","WITH","THIS","THAT","YOU",
    "YOUR","FROM","HOLD","BUY","SELL","PUT","CALL","LONG","SHORT","STOP","LOSS",
}
TOPICS = {
    "Sell Put": ["sell put","卖put","卖 put","sp "],
    "LEAPS": ["leap","leaps","长期期权"],
    "风险管理": ["风险","回撤","现金","保险","对冲","止损","爆仓","杠杆"],
    "失败复盘": ["认错","看错","失败","亏损","亏得","割肉","复盘"],
    "长期持有纪律": ["长期持有","长持","定投","time in the market","纪律","核心仓"],
    "仓位与加减仓": ["加仓","减仓","重仓","建仓","仓位","卖出一半"],
    "估值与价格": ["估值","价值","价格","margin of safety","安全边际"],
    "趋势确认": ["趋势","突破","false break","ma21","ma50","supertrend","tcds",
             "breakout","break out","strong close","hold above","new high","higher high",
             "consolidation","sideway","range bound","support","resistance","pullback"],
    "AI研究方法": ["chatgpt","claude","gemini","ai 炒股","ai研究","人工智能"],
}
ACTION_PATTERNS = [
    ("买入/建仓", r"买入|建仓|开始买|重仓|\benter(?:ed|ing)?\b|\bbought\b"),
    ("加仓", r"加仓|补仓|继续买|\badd(?:ed|ing)?\b"),
    ("减仓", r"减仓|卖掉一半|trim"),
    ("卖出/退出", r"卖出|清仓|割肉|退出|\bclosed?\b|take\s+profit|took\s+profit"),
    ("Sell Put", r"sell put|卖\s*put|\bsp\b"),
    ("LEAPS", r"leaps?|长期看涨期权"),
    ("对冲", r"对冲|买保险|protective put|hedge"),
]

def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def fetch_feed():
    try:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent":"MyAlphaView/SourceIntelligence"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data if isinstance(data, dict) else {"records":[]}
    except Exception as e:
        print("source feed unavailable:", e)
        return {"records":[]}

def symbols(text: str):
    raw = text or ""
    up = raw.upper()
    found = []
    for s in sorted(SYMBOLS, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(s)}(?![A-Z0-9])", up):
            found.append(s)

    # Historical reparse: forum posts often mention symbols that were not in the
    # original static universe. Infer only explicit uppercase ticker-like tokens.
    for token in re.findall(r"(?<![A-Za-z0-9])\$?([A-Z]{2,5})(?![A-Za-z0-9])", raw):
        if token in TICKER_BLOCKLIST:
            continue
        if token not in found:
            found.append(token)

    aliases = {"英特尔":"INTC","特斯拉":"TSLA","英伟达":"NVDA","谷歌":"GOOGL","摩根大通":"JPM"}
    for name, sym in aliases.items():
        if name in raw and sym not in found:
            found.append(sym)
    return found[:12]

def topics(text: str, hints=None):
    low = (text or "").lower()
    out = []
    for name, keys in TOPICS.items():
        if any(k in low for k in keys):
            out.append(name)
    for x in hints or []:
        if x not in out:
            out.append(x)
    return out[:8] or ["其他研究"]

def actions(text: str):
    out = []
    for name, pat in ACTION_PATTERNS:
        if re.search(pat, text or "", re.I):
            out.append(name)
    return out[:4]

THIRD_PARTY_TITLE_HINTS = ("段永平","巴菲特","德鲁肯米勒","斯坦利","芒格","Burry","伯里")
AUTHOR_TITLE_HINTS = ("我","我的","今天","为什么我","回顾","更新","手记","复盘")

def attribute_operation(title: str, op: dict) -> dict:
    """Conservative ownership classification using only source metadata.
    Full-text live ingestion may already provide a stronger attribution tag.
    """
    if op.get("attribution"):
        return op
    t = title or ""
    if any(x.lower() in t.lower() for x in THIRD_PARTY_TITLE_HINTS):
        op["attribution"] = "third_party_example"
        op["attribution_confidence"] = "high"
        return op
    has_plan_level = any(k in op for k in ("entry_1","entry_2","entry_below","exit_line","target_range","sell_put_strike"))
    if has_plan_level:
        op["attribution"] = "author_plan"
        op["attribution_confidence"] = "medium"
    elif any(x in t for x in AUTHOR_TITLE_HINTS):
        op["attribution"] = "author_action"
        op["attribution_confidence"] = "medium"
    else:
        op["attribution"] = "unconfirmed_author_context"
        op["attribution_confidence"] = "needs_review"
    return op

def seed_brightline():
    rows = []
    insights = load(FULLTEXT_INSIGHTS, {"articles":[]})
    insight_by_url = {re.sub(r"#.*$","",x.get("url","")): x for x in insights.get("articles", [])}
    for path in ARCHIVES:
        data = load(path, {"articles":[]})
        for a in data.get("articles", []):
            canonical = re.sub(r"#.*$","",a.get("url",""))
            learned = insight_by_url.get(canonical, {})
            rows.append({
                "id": "brightline-" + re.sub(r"\W+","-",a.get("url",""))[-50:],
                "source": "wenxuecity",
                "source_kind": "blog",
                "author": "BrightLine",
                "published_at": a.get("date",""),
                "title": a.get("title",""),
                "url": canonical,
                "excerpt": "",
                "content_chars": a.get("chars",0),
                "themes_hint": list(dict.fromkeys(([a.get("topic")] if a.get("topic") else []) + (learned.get("method_tags") or []))),
                "symbols": learned.get("symbols") or [],
                "operations": learned.get("operations") or [],
                "portfolio_rules": learned.get("portfolio_rules") or [],
                "lessons": learned.get("lessons") or [],
                "archive_only": not bool(learned),
                "fulltext_learning": bool(learned),
                "deep_analysis": bool(a.get("deep_analysis")),
                "source_notice": "BrightLine 原文索引；全文不在公开站点转载。",
            })
    return rows

def normalize(row):
    title = str(row.get("title") or "")
    excerpt = str(row.get("excerpt") or "")
    text = (title + "\n" + excerpt).strip()
    learned_ops = [attribute_operation(title, dict(op)) for op in (row.get("operations") or [])]
    def type_labels(values):
        out = []
        for value in values or []:
            label = value.get("type") if isinstance(value, dict) else str(value)
            if label and label not in out:
                out.append(label)
        return out
    learned_rules = type_labels(row.get("portfolio_rules") or [])
    learned_lessons = type_labels(row.get("lessons") or [])
    syms = list(dict.fromkeys((row.get("symbols") or []) + symbols(text)))
    tps = topics(text, row.get("themes_hint"))
    acts = actions(text)
    for op in learned_ops:
        for a in op.get("actions") or []:
            if a not in acts:
                acts.append(a)
    failure = bool(learned_lessons) or any(x in tps for x in ["失败复盘"]) or (any(x in acts for x in ["卖出/退出","clear"]) and bool(re.search(r"认错|看错|割肉|亏", text)))
    return {
        "id": row.get("id"),
        "source": row.get("source","wenxuecity"),
        "source_kind": row.get("source_kind","unknown"),
        "author": row.get("author","未知作者"),
        "published_at": row.get("published_at",""),
        "title": title,
        "url": row.get("url",""),
        "excerpt": excerpt[:900],
        "content_chars": row.get("content_chars",0),
        "symbols": syms,
        "topics": tps,
        "actions": acts,
        "operations": learned_ops,
        "portfolio_rules": learned_rules,
        "lessons": learned_lessons,
        "failure_candidate": bool(failure),
        "archive_only": bool(row.get("archive_only")),
        "deep_analysis": bool(row.get("deep_analysis")),
        "source_notice": row.get("source_notice") or "外部作者原始观点，仅作研究来源。",
        "myalpha_validation": "needs_independent_validation",
    }

def build(records):
    rows = [normalize(x) for x in records if x.get("url") or x.get("title")]
    dedup = {}
    for r in rows:
        key = re.sub(r"#.*$","",r.get("url") or "") or r.get("id")
        if key not in dedup or (r.get("excerpt") and not dedup[key].get("excerpt")):
            dedup[key] = r
    rows = sorted(dedup.values(), key=lambda x: x.get("published_at",""), reverse=True)

    by_topic = defaultdict(list)
    for r in rows:
        for t in r["topics"]:
            by_topic[t].append(r)

    method_counts = Counter()
    for r in rows:
        for t in r["topics"]:
            if t in {"Sell Put","LEAPS","风险管理","失败复盘","长期持有纪律","仓位与加减仓","估值与价格","趋势确认"}:
                method_counts[t] += 1

    evolutions = []
    histories = defaultdict(list)
    for r in rows:
        for sym in r["symbols"]:
            histories[(r["author"],sym)].append(r)
    for (author,sym), items in histories.items():
        items = sorted(items, key=lambda x: x.get("published_at",""))
        if len(items) >= 2:
            evolutions.append({
                "author": author,
                "symbol": sym,
                "count": len(items),
                "from": items[0].get("published_at"),
                "to": items[-1].get("published_at"),
                "latest_title": items[-1].get("title"),
                "latest_actions": items[-1].get("actions"),
                "status": "观点演变待复核",
                "note": "按同一作者/标的时间线聚合；不能仅凭动作变化推断作者完整观点已经反转。",
            })

    thesis_candidates = []
    by_symbol = defaultdict(list)
    for r in rows:
        for sym in r["symbols"]:
            by_symbol[sym].append(r)
    for sym, items in by_symbol.items():
        items = sorted(items, key=lambda x: x.get("published_at",""), reverse=True)
        thesis_candidates.append({
            "symbol": sym,
            "source_records": len(items),
            "authors": sorted(set(x["author"] for x in items)),
            "latest_title": items[0].get("title"),
            "latest_url": items[0].get("url"),
            "topics": sorted(set(t for x in items[:8] for t in x["topics"])),
            "candidate_hypothesis": "外部来源对该标的形成重复研究线索，值得与现有基本面、估值、趋势和事件证据交叉验证。",
            "validation_state": "candidate_only",
            "guardrail": "不是本站Thesis，也不是买卖信号；需MyAlpha独立验证后才能升级。",
        })

    alerts = []
    for r in rows:
        if r["archive_only"] and not r["operations"] and not r["portfolio_rules"] and not r["lessons"]:
            continue
        if not r["actions"] and not r["operations"] and not r["failure_candidate"] and not r["symbols"]:
            continue
        reason = []
        if r["actions"]: reason.append("出现明确操作：" + " / ".join(r["actions"]))
        if r["operations"]:
            price_ops = []
            for op in r["operations"][:4]:
                sym = "/".join(op.get("symbols") or [])
                fields = []
                if op.get("entry_1") is not None: fields.append(f"第一档 {op['entry_1']:g}")
                if op.get("entry_2") is not None: fields.append(f"第二档 {op['entry_2']:g}")
                if op.get("entry_below") is not None: fields.append(f"跌破 {op['entry_below']:g} 才考虑")
                if op.get("sell_put_strike") is not None: fields.append(f"Sell Put K={op['sell_put_strike']:g}")
                if op.get("exit_line") is not None: fields.append(f"卖出线 {op['exit_line']:g}")
                if op.get("target_range"): fields.append("目标区 " + "-".join(f"{x:g}" for x in op["target_range"]))
                if fields: price_ops.append((sym + " " + " / ".join(fields)).strip())
            if price_ops: reason.append("具体条件：" + "；".join(price_ops))
        if r["portfolio_rules"]: reason.append("组合规则：" + " / ".join(r["portfolio_rules"]))
        if r["symbols"]: reason.append("涉及：" + " / ".join(r["symbols"]))
        if r["failure_candidate"]: reason.append("可进入失败复盘")
        alerts.append({
            "author": r["author"],
            "title": r["title"],
            "url": r["url"],
            "published_at": r["published_at"],
            "symbols": r["symbols"],
            "topics": r["topics"],
            "source_view": "；".join(reason),
            "myalpha_view": "先核对行情、估值、事件与现有 Thesis；外部作者观点不能单独触发买卖。",
            "what_changes_view": "只有独立证据与后续结果支持，才允许升级为 Breadcrumb / Thesis 样本。",
            "priority": 80 if r["failure_candidate"] or len(r["actions"]) >= 1 else 60,
        })

    return {
        "version": 2,
        "parser_version": "5.9.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "收纳优先，来源明确；学习方法，不复制结论；外部操作先独立验证，再进入MyAlpha学习。",
        "authors": sorted(set(r["author"] for r in rows)),
        "counts": {
            "records": len(rows),
            "deep_analysis": sum(1 for r in rows if r["deep_analysis"]),
            "failure_candidates": sum(1 for r in rows if r["failure_candidate"]),
            "action_records": sum(1 for r in rows if r["operations"] or r["actions"]),
            "structured_operations": sum(len(r["operations"]) for r in rows),
            "portfolio_rule_records": sum(1 for r in rows if r["portfolio_rules"]),
            "lesson_records": sum(1 for r in rows if r["lessons"]),
            "historically_reparsed": len(rows),
        },
        "topic_groups": {k: v[:80] for k,v in sorted(by_topic.items(), key=lambda x: -len(x[1]))},
        "repeated_methods": [{"name":k,"records":v,"status":"research_candidate"} for k,v in method_counts.most_common()],
        "viewpoint_evolution": sorted(evolutions, key=lambda x: -x["count"])[:60],
        "thesis_candidates": sorted(thesis_candidates, key=lambda x: -x["source_records"])[:60],
        "failure_review": [r for r in rows if r["failure_candidate"]][:60],
        "operation_cases": [r for r in rows if r["operations"] or r["actions"]][:120],
        "owned_operation_cases": [
            r for r in rows
            if any((op.get("attribution") in {"author_action","author_plan"}) for op in r["operations"])
        ][:120],
        "third_party_examples": [
            r for r in rows
            if any((op.get("attribution") == "third_party_example") for op in r["operations"])
        ][:80],
        "portfolio_rules": [
            {"author": r["author"], "title": r["title"], "url": r["url"], "published_at": r["published_at"], "rules": r["portfolio_rules"]}
            for r in rows if r["portfolio_rules"]
        ][:80],
        "learning_lessons": [
            {"author": r["author"], "title": r["title"], "url": r["url"], "published_at": r["published_at"], "lessons": r["lessons"], "symbols": r["symbols"]}
            for r in rows if r["lessons"]
        ][:80],
        "research_alerts": sorted(alerts, key=lambda x: -x["priority"])[:24],
        "records": rows[:800],
        "guardrails": [
            "每条外部内容保留作者、日期、原文链接和来源类型。",
            "作者观点与MyAlpha独立分析必须分开展示。",
            "外部作者的买卖、价格、仓位或期权操作不自动成为本站交易规则。",
            "只有后续独立验证和成熟结果样本才可影响Breadcrumb/Failure Attribution学习层。",
            "系统不自动下单，不因单一外部观点修改QQQM/VGT/QLD核心规则。",
        ],
    }

def main():
    feed = fetch_feed()
    records = seed_brightline() + list(feed.get("records") or [])
    result = build(records)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
