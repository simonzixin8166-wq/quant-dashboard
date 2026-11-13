#!/usr/bin/env python3
"""Shock-event monitor: find unexpected events that move the market, record them, analyse them and advise.

Owner 2026-11-12 (after the Nvidia CEO event): unexpected events with market impact must be recorded, analysed
in time and come with advice. Runs twice a day on weekdays (before the US open and after the close).

Find (config/shock_watch.json): a big move of a mega-cap or core-index constituent (including pre/after-hours),
a big index/VIX move, or a cluster of shock headlines about one company from several publishers.
Record (append-only): research/archive/shock_events.jsonl holds event, observation and outcome rows.
Analyse: market reaction, the estimated effect on the core ETFs against the Owner's existing tiers, upcoming
scheduled events (earnings), and the follow-up returns after 1 / 5 / 20 NYSE sessions.
Advise: rule-based research hints consistent with the Owner's discipline; one Telegram message per event.

Free public data only (Yahoo Finance chart + search, as event_evidence_engine already uses); headlines are
stored as title / publisher / time / link only. Never orders, never changes tiers, thresholds or allocation.
Facts from headlines are "reported, not verified" until a company or official statement confirms them.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import core_tier_state as cts  # noqa: E402
import trading_calendar as tc  # noqa: E402

CONFIG = ROOT / "config" / "shock_watch.json"
TIERS = ROOT / "config" / "playbooks.public.json"
DATA = ROOT / "docs" / "data.json"
CALENDAR = ROOT / "docs" / "data" / "event_calendar.json"
LEDGER = ROOT / "research" / "archive" / "shock_events.jsonl"
STATE = ROOT / "research" / "store" / "shock_event_state.json"
OUT = ROOT / "docs" / "research" / "shock_events.json"
VERSION = "shock-1.0"
MERGE_SESSIONS = 2          # a new trigger on the same subject within this many sessions joins the open event
MAX_SEND_ATTEMPTS = 3
PUBLIC_EVENTS = 20
DISCLAIMER = "研究提示，不是买卖指令；是否操作由你决定。"
GOVERNANCE = ("ceo", "oust", "resign", "steps down", "fired", "probe", "investigat", "subpoena", "fraud",
              "scandal", "affair", "indicted", "罢免", "辞职", "调查", "丑闻")
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=5m&range=1d&includePrePost=true"
DAILY = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=3mo"
SEARCH = "https://query1.finance.yahoo.com/v1/finance/search?{q}"
UA = {"User-Agent": "Mozilla/5.0 MyAlphaView/6.4", "Accept": "application/json"}


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def _iso(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- data (network; replaced in tests)

def parse_chart(payload, sym):
    """Last price including pre/post-market, the previous regular close and the moves. Missing -> unavailable."""
    try:
        res = payload["chart"]["result"][0]
        meta = res["meta"]
        prev = float(meta["chartPreviousClose"])
        ts = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0]["close"]
        pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
        if not pts or prev <= 0:
            raise ValueError("no prices")
        t_last, last = pts[-1]
        reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        start, end = reg.get("start"), reg.get("end")
        session = "regular"
        if start and t_last < start:
            session = "pre"
        elif end and t_last >= end:
            session = "post"
        rmp, rmt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
        regular_close = float(rmp) if session == "post" and rmp else None
        if session == "pre" and rmp and rmt and start and rmt < start:
            # before the open the 1d chart still spans the previous session, so chartPreviousClose is the close
            # two sessions back; the last regular close is regularMarketPrice (production bug 2026-11-12)
            prev = float(rmp)
        total = last / prev - 1
        ext = (last / regular_close - 1) if regular_close else (total if session == "pre" else 0.0)
        day = (regular_close / prev - 1) if regular_close else (None if session == "pre" else total)
        today = (datetime.fromtimestamp(start, timezone.utc) - timedelta(hours=5)).date() if start else None
        # the reference is the last close before the move: an after-hours move that dominates the day is
        # measured from today's close, everything else from the previous close
        if regular_close and abs(ext) >= abs(day):
            ref, ref_price = today.isoformat() if today else None, regular_close
        else:
            ref, ref_price = (tc.previous_session(today).isoformat() if today else None), prev
        return {"symbol": sym, "status": "ok", "prev_close": round(prev, 4), "last": round(float(last), 4),
                "last_time": _iso(t_last), "session": session, "ref_session": ref, "ref_price": round(ref_price, 4),
                "move_total": round(total, 4), "move_ext": round(ext, 4),
                "move_day": None if day is None else round(day, 4)}
    except Exception as exc:
        return {"symbol": sym, "status": "unavailable", "reason": type(exc).__name__}


def anchor(q, data):
    """Re-measure a quote from the Daily close of its reference session (docs/data.json) when the dates match."""
    if q.get("status") != "ok" or not q.get("ref_session"):
        return q
    for group in ("core", "index", "stocks"):
        row = ((data or {}).get(group) or {}).get(q["symbol"]) or {}
        if row.get("date") == q["ref_session"] and isinstance(row.get("close"), (int, float)) and row["close"] > 0:
            ref = float(row["close"])
            q = dict(q, ref_price=round(ref, 4), anchor="daily_close")
            q["move_total"] = round(q["last"] / ref - 1, 4)
            if q.get("session") == "pre":
                q["move_ext"] = q["move_total"]
            return q
    return dict(q, anchor="chart_meta")


def fetch_quote(sym):
    try:
        return parse_chart(_get(CHART.format(sym=urllib.parse.quote(sym))), sym)
    except Exception as exc:
        return {"symbol": sym, "status": "unavailable", "reason": type(exc).__name__}


def fetch_news(sym):
    try:
        payload = _get(SEARCH.format(q=urllib.parse.urlencode({"q": sym, "quotesCount": 0, "newsCount": 20})))
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__, "items": []}
    items = []
    for x in payload.get("news") or []:
        if not x.get("title") or not x.get("providerPublishTime"):
            continue
        items.append({"title": x["title"][:200], "publisher": x.get("publisher") or "", "url": x.get("link"),
                      "published_at": _iso(x["providerPublishTime"]), "related": x.get("relatedTickers") or []})
    return {"status": "ok", "items": items}


def fetch_daily(sym):
    """{session: close} for the last ~3 months of regular sessions."""
    try:
        res = _get(DAILY.format(sym=urllib.parse.quote(sym)))["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(res.get("timestamp") or [], closes):
            if c is not None:
                out[(datetime.fromtimestamp(t, timezone.utc) - timedelta(hours=5)).date().isoformat()] = float(c)
        return out
    except Exception:
        return {}


# ---------------------------------------------------------------- detection (pure)

def _kw_hit(title, keywords):
    t = title.lower()
    for k in keywords:
        k = k.lower()
        if re.fullmatch(r"[a-z ]+", k):
            if re.search(r"\b" + re.escape(k) + r"(?:s|es|ed|ing)?\b", t):
                return k
        elif k in t:
            return k
    return None


def _names(title, cfg):
    t = title.lower()
    return {s for s, al in cfg["stocks"].items() if any(a.lower() in t for a in al) or re.search(r"\b" + s + r"\b", title)}


def news_cluster(sym, aliases, news, cfg, now):
    """Headlines naming two or more watched companies ("AMD, Broadcom gain after Nvidia board ...") are peer
    reactions: they never count toward one company's cluster (production false trigger AVGO 2026-11-12)."""
    th = cfg["thresholds"]
    since = now - timedelta(hours=th["news_window_hours"])
    hits, publishers = [], set()
    for x in news:
        try:
            when = datetime.fromisoformat(x["published_at"])
        except Exception:
            continue
        title = x["title"]
        about = any(a.lower() in title.lower() for a in aliases) or re.search(r"\b" + sym + r"\b", title) is not None
        kw = _kw_hit(title, cfg["keywords"])
        if when >= since and about and kw and len(_names(title, cfg)) <= 1:
            hits.append(dict(x, keyword=kw))
            publishers.add((x.get("publisher") or "").strip().lower())
    return {"hit": len(publishers) >= th["news_publishers"], "publishers": len(publishers), "items": hits}


def metric(q):
    return max(abs(q.get("move_total") or 0.0), abs(q.get("move_ext") or 0.0))


def detect(quotes, news, cfg, now):
    th = cfg["thresholds"]
    out = []
    for sym, aliases in cfg["stocks"].items():
        q = quotes.get(sym) or {}
        price = q.get("status") == "ok" and metric(q) >= th["stock_move"]
        nc = news_cluster(sym, aliases, (news.get(sym) or {}).get("items") or [], cfg, now)
        if price or nc["hit"]:
            out.append({"subject": sym, "kind": "company", "price_trigger": bool(price), "news_trigger": nc["hit"],
                        "severity": "high" if price and nc["hit"] else "medium", "quote": q, "news": nc})
    mkt = [s for s in cfg["market"] if (quotes.get(s) or {}).get("status") == "ok" and metric(quotes[s]) >= th["market_move"]]
    v = quotes.get(cfg["vix"]) or {}
    vix = v.get("status") == "ok" and ((v.get("move_total") or 0) >= th["vix_jump"] or v.get("last", 0) >= th["vix_level"])
    if mkt or vix:
        out.append({"subject": "MARKET", "kind": "market", "price_trigger": True, "news_trigger": False,
                    "severity": "high" if mkt and vix else "medium", "market_movers": mkt, "vix_trigger": bool(vix)})
    return out


# ---------------------------------------------------------------- analysis and advice (pure)

def core_impact(cfg, quotes, data, tiers_all):
    rows = []
    core = (data or {}).get("core") or {}
    for sym in cfg["core"]:
        row, tiers = core.get(sym), tiers_all.get(sym)
        loss, ath, why = cts.row_inputs(row, tiers)
        if loss is None:
            rows.append({"symbol": sym, "status": "unavailable", "reason": why})
            continue
        q = quotes.get(sym) or {}
        src = sym
        if q.get("status") != "ok" and cfg.get("core_proxy", {}).get(sym):
            src = cfg["core_proxy"][sym]
            q = quotes.get(src) or {}
        if q.get("status") != "ok":
            rows.append({"symbol": sym, "status": "unavailable", "reason": "no_quote"})
            continue
        # the Daily row holds the last completed close (= the quote's previous close at both run times)
        price = float(row["close"]) * (1 + q["move_total"])
        dd = price / ath - 1
        th = cts.thresholds(tiers)
        reached = [k for k in ("near", "t1", "t2", "t3") if -dd >= th[k]]
        ahead = next((k for k in ("near", "t1", "t2", "t3") if -dd < th[k]), None)
        rows.append({"symbol": sym, "status": "ok", "price_source": src, "move": q["move_total"],
                     "est_drawdown": round(dd, 4), "close_drawdown": round(float(row["strategy_drawdown"]), 4),
                     "reached": reached[-1] if reached else None, "next_line": ahead,
                     "to_next_line": None if ahead is None else round(th[ahead] + dd, 4),
                     "thresholds": th, "estimated": True})
    return rows


def upcoming(sym, calendar, today, days=10):
    rows = []
    for e in (calendar or {}).get("events") or []:
        try:
            d = date.fromisoformat(e.get("date", ""))
        except Exception:
            continue
        if e.get("symbol") == sym and today <= d <= today + timedelta(days=days):
            rows.append({"date": e["date"], "title_zh": e.get("title_zh"), "time_status": e.get("time_status")})
    return rows


SESSION_ZH = {"pre": "盘前", "post": "盘后", "regular": "盘中"}
LINE_ZH = {"near": "接近一级", "t1": "一级", "t2": "二级", "t3": "三级"}


def advice(ev, impact, events_ahead, others=()):
    tips = []
    hit = [r for r in impact if r.get("status") == "ok" and r.get("reached")]
    if hit:
        s = "；".join(f"{r['symbol']} 估算回撤 {-r['est_drawdown']:.1%}，已到{LINE_ZH[r['reached']]}线" for r in hit)
        tips.append(f"核心仓位：{s}。按原有分级计划执行，正式提醒以收盘数据为准，不因单一事件改变节奏。")
    else:
        near = [r for r in impact if r.get("status") == "ok" and r.get("next_line")]
        s = "；".join(f"{r['symbol']} 距{LINE_ZH[r['next_line']]}线还差 {r['to_next_line']:.1%}" for r in near)
        tips.append(f"核心仓位：{s or '数据不可用'}。按原计划定投，不因单一事件改变节奏。")
    if ev["kind"] == "company":
        titles = " ".join(x["title"].lower() for x in ev["news"]["items"])
        if ev["news_trigger"] and any(g in titles for g in GOVERNANCE):
            tips.append(f"{ev['subject']}：管理层或治理事件，结果未定。不建议因下跌加仓，也不建议恐慌卖出；等公司或董事会正式公告。")
        else:
            tips.append(f"{ev['subject']}：原因未经核实前，不据此调整仓位；先看是否有公司公告或官方消息。")
            if others:
                tips.append(f"同期 {'、'.join(others)} 也有事件，两者可能相关（未核实）。")
        if events_ahead:
            tips.append(f"{ev['subject']}：{events_ahead[0]['date']} 有{events_ahead[0].get('title_zh') or '已排期事件'}"
                        "（日期以公司公告为准），两个不确定性叠加。")
        tips.append(f"期权：事件期间隐含波动率通常上升、跳空风险大，不建议在结果明确前新开 {ev['subject']} 期权仓位。")
    else:
        tips.append("市场层面波动：先看核心分级是否触发；QLD 是两倍杠杆，波动和回撤都更大。")
    tips.append(DISCLAIMER)
    return tips


def reaction(cfg, quotes):
    keys = cfg["market"] + [cfg["vix"]] + [s for s in cfg["core"] if s not in cfg["market"]]
    return {s: {k: (quotes.get(s) or {}).get(k) for k in ("status", "last", "move_total", "move_ext", "session")}
            for s in keys}


# ---------------------------------------------------------------- ledger, follow-ups, delivery

def read_ledger(path):
    rows = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def append(path, rows):
    if not rows:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def open_event(ledger, subject, ref):
    for r in reversed(ledger):
        if r.get("type") == "event" and r.get("subject") == subject and r.get("ref_session") and ref:
            gap = len(tc.sessions_between(r["ref_session"], ref)) if ref >= r["ref_session"] else 0
            if gap <= MERGE_SESSIONS:
                return r
    return None


CORRECTABLE = ("quote", "core_impact", "advice", "severity", "price_trigger", "reaction")


def apply_corrections(e, rows):
    """Public view of an event after its append-only correction rows (the original event row is never rewritten)."""
    if not rows:
        return e
    e = dict(e)
    for c in sorted(rows, key=lambda r: r.get("at", "")):
        for k in CORRECTABLE:
            if k in c:
                e[k] = c[k]
        if c.get("retracted"):
            e["retracted"] = True
        e.setdefault("corrections", []).append({"at": c.get("at"), "reason_zh": c.get("reason_zh")})
    return e


def telegram_text(e):
    head = f"MyAlpha｜突发事件：{e['subject']}" + ("（价格+新闻）" if e["severity"] == "high" else "")
    lines = [head]
    q = e.get("quote") or {}
    if q.get("status") == "ok":
        when = SESSION_ZH.get(q.get("session"), "")
        lines.append(f"{e['subject']} 相对前收 {q['move_total']:+.1%}（{when}，{q['last_time'][11:16]} UTC）")
    for x in (e.get("headlines") or [])[:3]:
        lines.append(f"· {x['publisher']}：{x['title'][:90]}")
    if e.get("headlines"):
        lines.append("以上为媒体报道，未经核实。")
    lines += e["advice"]
    return "\n".join(lines)


def follow_ups(ledger, cfg, last_completed, daily):
    """Append outcome rows for events whose +n session has completed (never rewritten)."""
    done = {(r["event_id"], r["n"]) for r in ledger if r.get("type") == "outcome"}
    rows, cache = [], {}
    for e in (r for r in ledger if r.get("type") == "event"):
        for n in cfg["follow_up_sessions"]:
            if (e["event_id"], n) in done or not e.get("ref_session"):
                continue
            target = tc.add_sessions(e["ref_session"], n).isoformat()
            if target > last_completed:
                continue
            out = {"type": "outcome", "event_id": e["event_id"], "n": n, "session": target}
            for sym in ([e["subject"]] if e["kind"] == "company" else []) + ["QQQ"]:
                closes = cache.setdefault(sym, daily(sym))
                ref, tgt = closes.get(e["ref_session"]), closes.get(target)
                out[sym] = None if not (ref and tgt) else round(tgt / ref - 1, 4)
            if any(out.get(s) is not None for s in ("QQQ", e["subject"])):
                rows.append(out)
    return rows


def run(now=None, quote=fetch_quote, news=fetch_news, daily=fetch_daily, send=None, cfg=None, data=None,
        tiers=None, calendar=None, ledger_path=LEDGER, state_path=STATE, out_path=OUT, pause=0.4):
    now = now or datetime.now(timezone.utc)
    cfg = cfg or load(CONFIG)
    data = data if data is not None else load(DATA, {})
    tiers = tiers if tiers is not None else (load(TIERS, {}) or {}).get("core_tiers") or {}
    calendar = calendar if calendar is not None else load(CALENDAR, {})
    send = send or notify
    symbols = list(cfg["stocks"]) + cfg["market"] + [cfg["vix"]] + [s for s in cfg["core"] if s not in cfg["market"]]
    quotes, headlines = {}, {}
    for s in symbols:
        quotes[s] = anchor(quote(s), data)
        time.sleep(pause)
    for s in cfg["stocks"]:
        headlines[s] = news(s)
        time.sleep(pause)
    ledger = read_ledger(ledger_path)
    state = load(state_path, {}) or {}
    impact = core_impact(cfg, quotes, data, tiers)
    new_rows, touched = [], []
    found = detect(quotes, headlines, cfg, now)
    for ev in found:
        q = ev.get("quote") or quotes.get("QQQ") or {}
        ref = q.get("ref_session") or tc.previous_session(now).isoformat()
        prior = open_event(ledger + new_rows, ev["subject"], ref)
        obs = {"type": "observation", "at": now.isoformat(timespec="seconds"), "subject": ev["subject"],
               "severity": ev["severity"], "price_trigger": ev["price_trigger"], "news_trigger": ev["news_trigger"],
               "quote": {k: q.get(k) for k in ("last", "move_total", "move_ext", "session", "last_time")}}
        if prior:
            obs["event_id"] = prior["event_id"]
            new_rows.append(obs)
            touched.append(prior["event_id"])
            continue
        eid = f"{ev['subject']}@{ref}"
        items = sorted(ev.get("news", {}).get("items", []), key=lambda x: x["published_at"], reverse=True)
        ahead = upcoming(ev["subject"], calendar, now.date()) if ev["kind"] == "company" else []
        e = {"type": "event", "event_id": eid, "version": VERSION, "first_seen": now.isoformat(timespec="seconds"),
             "subject": ev["subject"], "kind": ev["kind"], "severity": ev["severity"], "ref_session": ref,
             "price_trigger": ev["price_trigger"], "news_trigger": ev["news_trigger"],
             "quote": {k: q.get(k) for k in ("status", "prev_close", "ref_price", "last", "move_total", "move_ext", "move_day", "session", "last_time")},
             "headlines": [{k: x.get(k) for k in ("title", "publisher", "published_at", "url", "keyword")} for x in items[:8]],
             "facts_status": "reported_unverified" if items else "price_only",
             "market_movers": ev.get("market_movers"), "vix_trigger": ev.get("vix_trigger"),
             "reaction": reaction(cfg, quotes), "core_impact": impact, "upcoming": ahead,
             "production_use": False}
        e["advice"] = advice(ev, impact, ahead, [x["subject"] for x in found if x["subject"] not in (ev["subject"], "MARKET")])
        if ev["kind"] == "company" and any(a["date"] in (ref, now.date().isoformat()) for a in ahead):
            e["scheduled"] = "earnings"
        new_rows.append(e)
        obs["event_id"] = eid
        new_rows.append(obs)
        state.setdefault(eid, {"attempts": 0, "status": "pending"})
    last_completed = str(tc.expected_latest_completed_session(now))[:10]
    new_rows += follow_ups(ledger + new_rows, cfg, last_completed, daily)
    append(ledger_path, new_rows)
    ledger += new_rows
    events = {r["event_id"]: r for r in ledger if r.get("type") == "event"}
    for eid, st in state.items():
        if st.get("status") in ("sent", "disabled") or st.get("attempts", 0) >= MAX_SEND_ATTEMPTS or eid not in events:
            continue
        d = send(telegram_text(events[eid]))
        st["attempts"] = st.get("attempts", 0) + 1
        st["status"] = "sent" if d == "sent" else ("disabled" if d in ("disabled", "not_configured") else "failed")
        st["last_delivery"] = d
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    outcomes = {}
    for r in ledger:
        if r.get("type") == "outcome":
            outcomes.setdefault(r["event_id"], []).append(r)
    public = []
    for e in sorted(events.values(), key=lambda r: r["first_seen"], reverse=True)[:PUBLIC_EVENTS]:
        e = apply_corrections(e, [r for r in ledger if r.get("type") == "correction" and r.get("event_id") == e["event_id"]])
        public.append(dict(e, outcomes=sorted(outcomes.get(e["event_id"], []), key=lambda r: r["n"]),
                           delivery=(state.get(e["event_id"]) or {}).get("status")))
    unavailable = sorted(s for s, q in quotes.items() if q.get("status") != "ok")
    report = {"version": VERSION, "generated_at": now.isoformat(timespec="seconds"),
              "checked": {"quotes": len(quotes), "unavailable": unavailable,
                          "news": sum(1 for v in headlines.values() if v.get("status") == "ok")},
              "new_events": [r["event_id"] for r in new_rows if r.get("type") == "event"],
              "updated_events": sorted(set(touched)), "events": public, "learning_state": "UNPROVEN",
              "production_use": False,
              "policy_zh": "只用免费公开行情和新闻标题；媒体报道标为未核实；建议是研究提示，不下单、不改阈值和仓位。"}
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return report


def notify(text):
    if os.getenv("SHOCK_ALERTS_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return "disabled"
    from daily_guardian import send_telegram
    return send_telegram(text)


def main():
    r = run()
    print(f"shock_event_monitor: new={r['new_events']} updated={r['updated_events']} "
          f"unavailable={r['checked']['unavailable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
