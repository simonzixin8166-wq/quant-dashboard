#!/usr/bin/env python3
"""External source intelligence -> MyAlpha research-learning layer.

The engine preserves provenance and separates:
1) what an external author said/did;
2) MyAlpha's own validation state;
3) whether the item is only a research alert or has matured into a learning sample.

It never changes core trading thresholds and never issues automatic orders.
"""
from __future__ import annotations
import base64, json, os, re, urllib.request
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
YOUTUBE_ARCHIVE_URL = os.getenv(
    "YOUTUBE_LEARNING_ARCHIVE_URL",
    "https://raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/youtube_learning_archive.json",
)

SYMBOLS = {
    "INTC","IREN","TSLA","QQQ","QQQM","VGT","QLD","TQQQ","NVDA","MU","AMZN",
    "NOW","META","SMH","SPY","VOO","ORCL","IBIT","BTC","COIN","NBIS","CRWV","SNDK",
    "PYPL","GOOG","GOOGL","AAPL","MSFT","AMD","TSM","AVGO","JPM","AMAT","LITE","BE","MRVL","RSP","QCOM","AAOI","CIEN",
}
# Uppercase tokens from forum titles are useful ticker candidates, but a conservative
# blocklist prevents common English abbreviations from becoming symbols.
TICKER_BLOCKLIST = {
    "AI","CEO","CFO","CTO","COO","SEC","FED","FOMC","CPI","PPI","GDP","EPS","PE",
    "DCF","ATH","ATL","LOL","IMO","IMHO","FYI","MM","SP","CC","DTE","IV","OI","RSI",
    "MA","TA","USD","US","ETF","ETFS","THE","AND","BUT","FOR","WITH","THIS","THAT","YOU",
    "YOUR","FROM","HOLD","BUY","SELL","PUT","CALL","LONG","SHORT","STOP","LOSS",
    "YOY","DCA","LEAP","LEAPS","FOMO","YTD","ROI","ER","IPO","CAPEX","FCF","HDD","HBM",
    "PEG","PCE","MACD","YMYD","RR","FA","PT","CNN","ID","DT","ES",
}
AMBIGUOUS_WORD_TICKERS = {"NOW","BE","META","LITE","COIN","MU","ARM","APP","ES","ID","DT"}
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
    ("卖出/退出", r"卖出|清仓|割肉|退出|\bclose(?:d)?\s+(?:sp|put|call|position|trade)\b|take\s+profit|took\s+profit"),
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
    """Fetch the latest wxc-bot research feed from GitHub's contents API.

    The contents API is used as the primary path because raw.githubusercontent.com
    may briefly serve a stale CDN copy immediately after a source-feed push.
    """
    api_url = "https://api.github.com/repos/simonzixin8166-wq/wxc-bot/contents/state/research_feed.json?ref=main"
    headers = {
        "User-Agent": "MyAlphaView/SourceIntelligence",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("content"):
            raw = base64.b64decode(str(payload["content"]).replace("\\n", "")).decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print("contents api source feed unavailable:", e)

    # Free public fallback. Keep it no-cache, but do not rely on it for same-cycle freshness.
    try:
        sep = "&" if "?" in FEED_URL else "?"
        live_url = FEED_URL + sep + "myalpha_cache_bust=" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        req = urllib.request.Request(live_url, headers={
            "User-Agent":"MyAlphaView/SourceIntelligence",
            "Cache-Control":"no-cache",
            "Pragma":"no-cache",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data if isinstance(data, dict) else {"records":[]}
    except Exception as e:
        print("source feed unavailable:", e)
        return {"records":[]}

def fetch_youtube_learning_archive():
    try:
        req = urllib.request.Request(YOUTUBE_ARCHIVE_URL, headers={"User-Agent":"MyAlphaView/SourceIntelligence"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print("youtube learning archive unavailable:", e)
        return {}

def symbols(text: str):
    raw = text or ""
    up = raw.upper()
    found = []
    for s in sorted(SYMBOLS, key=len, reverse=True):
        # Some valid tickers are common English words. Require explicit uppercase
        # spelling for those so prose such as "620 now" or "should be" is not tagged.
        haystack = raw if s in AMBIGUOUS_WORD_TICKERS else up
        if re.search(rf"(?<![A-Z0-9]){re.escape(s)}(?![A-Z0-9])", haystack):
            found.append(s)

    # Historical reparse: do not treat every uppercase finance/English token as
    # a ticker. Unknown symbols require an explicit $ prefix; otherwise they must
    # already be in the maintained symbol universe above.
    for match in re.finditer(r"(?<![A-Za-z0-9])(\$?)([A-Z]{2,5})(?![A-Za-z0-9])", raw):
        prefix,token=match.group(1),match.group(2)
        if token in TICKER_BLOCKLIST:
            continue
        if token not in SYMBOLS and prefix!="$":
            continue
        if token not in found:
            found.append(token)

    aliases = {"英特尔":"INTC","特斯拉":"TSLA","英伟达":"NVDA","谷歌":"GOOGL","摩根大通":"JPM"}
    for name, sym in aliases.items():
        if name in raw and sym not in found:
            found.append(sym)
    return found[:12]

def sanitize_declared_symbols(values, text: str):
    """Revalidate upstream ticker metadata against source text.

    The collector can provide useful symbols even when an excerpt is short, so
    non-ambiguous known tickers remain trusted. Common-English tickers (NOW/BE)
    and blocked abbreviations must have explicit source-text evidence.
    """
    raw = text or ""
    out = []
    for value in values or []:
        sym = str(value or "").upper().strip().lstrip("$")
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,5}", sym):
            continue
        if sym in TICKER_BLOCKLIST:
            continue
        explicit=bool(re.search(rf"(?<![A-Za-z0-9])\$?{re.escape(sym)}(?![A-Za-z0-9])", raw))
        if sym in AMBIGUOUS_WORD_TICKERS and not explicit:
            continue
        # Unknown upstream metadata is accepted only when the symbol is actually
        # present in the source text; maintained symbols may survive short excerpts.
        if sym not in SYMBOLS and not explicit:
            continue
        if sym not in out:
            out.append(sym)
    return out[:12]


def _symbol_present(sym: str, text: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9])\$?{re.escape(str(sym))}(?![A-Za-z0-9])", str(text or ""), re.I))

def _near_hint(sym: str, text: str, hints, radius=36) -> bool:
    raw=str(text or "")
    for m in re.finditer(rf"(?<![A-Za-z0-9])\$?{re.escape(str(sym))}(?![A-Za-z0-9])",raw,re.I):
        # Keep attribution inside the same sentence/semicolon-delimited clause.
        # This prevents "holding NVDA; for example AMD" from making AMD a holding.
        left=max(raw.rfind(ch,0,m.start()) for ch in ("。","！","？","!","?","；",";","\n"))+1
        rights=[p for ch in ("。","！","？","!","?","；",";","\n") if (p:=raw.find(ch,m.end()))!=-1]
        right=min(rights) if rights else len(raw)
        lo=max(left,m.start()-radius);hi=min(right,m.end()+radius)
        window=raw[lo:hi].lower()
        if any(str(h).lower() in window for h in hints):
            return True
    return False

def attribute_symbol_roles(row, syms, title, excerpt, learned_ops):
    """Conservative Primary Subject Attribution.

    Roles are descriptive provenance only. A primary subject is assigned only
    when the source itself provides a strong anchor; ambiguous multi-symbol
    articles remain contextual instead of forcing a false primary.
    """
    syms=[str(x).upper() for x in syms or [] if str(x)]
    title_syms=[s for s in syms if _symbol_present(s,title)]
    roles={s:{
        "symbol":s,"role":"contextual_mention","confidence":"low",
        "evidence_basis":["detected_in_source"]
    } for s in syms}

    def promote(sym,role,confidence,basis):
        if sym not in roles:return
        rank={"contextual_mention":0,"example_mention":1,"holding_mention":2,"comparison_peer":2,"primary_subject":3}
        cur=roles[sym]
        if rank.get(role,0)>=rank.get(cur.get("role"),0):
            cur["role"]=role;cur["confidence"]=confidence
        if basis not in cur["evidence_basis"]:cur["evidence_basis"].append(basis)

    # Explicit upstream primary metadata, when present, is still constrained to
    # the sanitized symbol universe.
    declared=[]
    for key in ("primary_symbol","primary_symbols"):
        value=row.get(key)
        vals=value if isinstance(value,list) else ([value] if value else [])
        for s in vals:
            sym=str(s).upper().strip().lstrip("$")
            if sym in syms and sym not in declared:declared.append(sym)
    for s in declared:promote(s,"primary_subject","high","upstream_explicit_primary")

    # Author-owned structured operations are the strongest local evidence.
    for op in learned_ops or []:
        if (op.get("attribution") or "") not in {"author_action","author_plan"}:continue
        for s in op.get("symbols") or []:
            sym=str(s).upper().strip().lstrip("$")
            if sym in syms:promote(sym,"primary_subject","high","author_owned_structured_operation")

    # A single title ticker is a strong subject anchor. Multiple title tickers
    # are not forced into primary/secondary unless the prose itself distinguishes them.
    if len(title_syms)==1:
        promote(title_syms[0],"primary_subject","high","unique_title_symbol")

    text=(str(title or "")+"\n"+str(excerpt or "")).strip()
    comparison_hints=(" vs "," versus ","对比","相比","比较","还是","相较")
    example_hints=("例如","比如","举例","example","e.g.","for example")
    holding_hints=("持有","持仓","仓位","成本","holding","position","own ")

    for s in syms:
        if _near_hint(s,text,example_hints):
            promote(s,"example_mention","medium","example_language")
        if _near_hint(s,text,holding_hints):
            promote(s,"holding_mention","medium","holding_language")

    # Comparison language only marks non-primary peers; it never demotes an
    # already explicit primary subject.
    if len(syms)>=2 and any(h.lower() in text.lower() for h in comparison_hints):
        primaries={s for s,v in roles.items() if v["role"]=="primary_subject"}
        for s in syms:
            if s not in primaries and _symbol_present(s,text):
                promote(s,"comparison_peer","medium","comparison_language")

    primary=[s for s in syms if roles[s]["role"]=="primary_subject"]
    return [roles[s] for s in syms],primary[:4]

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
    method_signals=[]
    for sig in row.get("method_signals") or []:
        if not isinstance(sig,dict) or not sig.get("condition_id"):
            continue
        method_signals.append({
            "condition_id":str(sig.get("condition_id"))[:80],
            "machine_ready":bool(sig.get("machine_ready")),
            "evidence_excerpt":str(sig.get("evidence_excerpt") or "")[:180],
            "evidence_hash":str(sig.get("evidence_hash") or "")[:64],
            "source_derived_only":bool(sig.get("source_derived_only",True)),
            "state_hint":str(sig.get("state_hint") or "")[:40] or None,
        })
    syms = list(dict.fromkeys(sanitize_declared_symbols(row.get("symbols"), text) + symbols(text)))
    symbol_attribution, primary_symbols = attribute_symbol_roles(row, syms, title, excerpt, learned_ops)
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
        "primary_symbols": primary_symbols,
        "symbol_attribution": symbol_attribution,
        "topics": tps,
        "actions": acts,
        "operations": learned_ops,
        "portfolio_rules": learned_rules,
        "lessons": learned_lessons,
        "method_signals": method_signals[:12],
        "failure_candidate": bool(failure),
        "archive_only": bool(row.get("archive_only")),
        "deep_analysis": bool(row.get("deep_analysis")),
        "source_notice": row.get("source_notice") or "外部作者原始观点，仅作研究来源。",
        "source_role": row.get("source_role"),
        "transcript_status": row.get("transcript_status"),
        "content_quality": row.get("content_quality"),
        "content_provider": row.get("content_provider"),
        "content_provider_url": row.get("content_provider_url"),
        "content_origin": row.get("content_origin"),
        "timestamp_evidence": bool(row.get("timestamp_evidence")),
        "rule_candidate_allowed": row.get("rule_candidate_allowed"),
        "captured_at": row.get("captured_at"),
        "intake_class_hint": row.get("intake_class_hint"),
        "capture_mode": row.get("capture_mode"),
        "myalpha_validation": "needs_independent_validation",
    }

def normalize_records(records):
    """Return the complete normalized/deduplicated source stream.

    This is the canonical pre-window stream. Callers that need persistent
    research ingestion must use this function rather than the public rows[:800]
    presentation window.
    """
    rows = [normalize(x) for x in records if x.get("url") or x.get("title")]
    dedup = {}
    for r in rows:
        key = re.sub(r"#.*$","",r.get("url") or "") or r.get("id")
        if key not in dedup or (r.get("excerpt") and not dedup[key].get("excerpt")):
            dedup[key] = r
    return sorted(dedup.values(), key=lambda x: x.get("published_at",""), reverse=True)

def collect_full_records_with_accounting():
    """Return one live raw->eligible->deduplicated reconciliation snapshot."""
    feed = fetch_feed()
    raw = seed_brightline() + list(feed.get("records") or [])
    eligible = [x for x in raw if x.get("url") or x.get("title")]
    normalized = normalize_records(raw)
    accounting = {
        "upstream_raw_records": len(raw),
        "eligible_raw_records": len(eligible),
        "normalized_unique_records": len(normalized),
        "duplicates_removed": max(0, len(eligible)-len(normalized)),
        "excluded_missing_identity": max(0, len(raw)-len(eligible)),
    }
    accounting["reconciliation_ok"] = (
        accounting["upstream_raw_records"]
        == accounting["eligible_raw_records"] + accounting["excluded_missing_identity"]
        and accounting["eligible_raw_records"]
        == accounting["normalized_unique_records"] + accounting["duplicates_removed"]
    )
    return normalized, accounting

def collect_full_records():
    return collect_full_records_with_accounting()[0]

def historical_learning_block(payload=None):
    """Bridge historical learning into Source Intelligence without admitting it to evidence intake.

    The upstream archive is treated as untrusted descriptive input. Eligibility
    flags that could affect forward evidence are force-closed again here so a
    future collector regression cannot promote historical material.
    """
    src = payload if isinstance(payload, dict) else {}
    records = []
    for raw in src.get("records") or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["forward_evidence_eligible"] = False
        row["promotion_eligible"] = False
        row["event_score_eligible"] = False
        row["source_store_eligible"] = False
        row["rule_registry_eligible"] = False
        row["non_gating"] = True
        records.append(row)
    upstream_counts = src.get("counts") if isinstance(src.get("counts"), dict) else {}
    counts = dict(upstream_counts)
    counts["records"] = len(records)
    counts["q1_q2_learning_eligible"] = sum(
        1 for r in records
        if r.get("historical_learning_eligible") and str(r.get("quality") or "").upper() in {"Q1","Q2"}
    )
    counts["structured_operations"] = sum(len(r.get("operations") or []) for r in records)
    return {
        "version": src.get("version", 1),
        "source": "wxc-bot/state/youtube_learning_archive.json",
        "upstream_generated_at": src.get("generated_at"),
        "mode": "historical_observational_learning_only",
        "non_gating": True,
        "result_blind": True,
        "records": records,
        "counts": counts,
        "guardrails": [
            "Historical learning is a top-level descriptive block, never part of Source Intelligence records.",
            "Historical learning never enters Source Store, Rule Registry, EventScore, Promotion, Readiness, Planner gating, or orders.",
            "All forward_evidence_eligible / promotion_eligible / event_score_eligible flags are force-closed at the bridge.",
            "Only Q1/Q2 historical text may contribute structured learning; lower-quality material remains context-only.",
        ],
    }

def build(records, youtube_historical_learning=None):
    rows = normalize_records(records)

    by_topic = defaultdict(list)
    for r in rows:
        for t in r["topics"]:
            by_topic[t].append(r)

    method_counts = Counter()
    for r in rows:
        for t in r["topics"]:
            if t in {"Sell Put","LEAPS","风险管理","失败复盘","长期持有纪律","仓位与加减仓","估值与价格","趋势确认"}:
                method_counts[t] += 1

    subject_role_counts=Counter(
        a.get("role") or "unknown"
        for r in rows for a in (r.get("symbol_attribution") or [])
    )
    evolutions = []
    histories = defaultdict(list)
    for r in rows:
        for sym in r.get("primary_symbols") or []:
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
        for sym in r.get("primary_symbols") or []:
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
        if r.get("primary_symbols"): reason.append("主研究标的：" + " / ".join(r["primary_symbols"]))
        if r["symbols"]: reason.append("涉及：" + " / ".join(r["symbols"]))
        if r["failure_candidate"]: reason.append("可进入失败复盘")
        alerts.append({
            "author": r["author"],
            "title": r["title"],
            "url": r["url"],
            "published_at": r["published_at"],
            "symbols": r["symbols"],
            "primary_symbols": r.get("primary_symbols") or [],
            "symbol_attribution": r.get("symbol_attribution") or [],
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
            "records_with_primary_subject": sum(1 for r in rows if r.get("primary_symbols")),
            "ambiguous_multi_symbol_records": sum(1 for r in rows if len(r.get("symbols") or [])>1 and not r.get("primary_symbols")),
            "symbol_role_counts": dict(subject_role_counts),
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
        "historical_learning": historical_learning_block(youtube_historical_learning),
        "records": rows[:800],
        "guardrails": [
            "每条外部内容保留作者、日期、原文链接和来源类型。",
            "作者观点与MyAlpha独立分析必须分开展示。",
            "Primary Subject Attribution 区分主研究标的、比较标的、持仓提及、举例股票；无法明确主标的时不强行归因。",
            "Thesis候选与观点演变只使用 primary_subject；比较/持仓/举例股票仅保留研究上下文。",
            "外部作者的买卖、价格、仓位或期权操作不自动成为本站交易规则。",
            "只有后续独立验证和成熟结果样本才可影响Breadcrumb/Failure Attribution学习层。",
            "系统不自动下单，不因单一外部观点修改QQQM/VGT/QLD核心规则。",
        ],
    }

def main():
    feed = fetch_feed()
    records = seed_brightline() + list(feed.get("records") or [])
    result = build(records, youtube_historical_learning=fetch_youtube_learning_archive())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
