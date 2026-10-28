#!/usr/bin/env python3
"""UX-02 event calendar (display only).

Combines, for the next WINDOW_DAYS days:
  - FOMC / CPI from docs/data/market_events.json (official Fed / BLS; produced by update_market_events.py)
  - official release DATES from the St. Louis Fed (FRED) release calendar: Employment Situation (non-farm
    payrolls), PPI, GDP, Personal Income and Outlays (PCE) - and CPI as a cross-check when BLS is only cached.
    FRED gives dates; the 08:30 ET time is the agencies' standing practice and is labelled as such.
  - earnings dates for the public watchlist (docs/data.json "stocks") from Yahoo via yfinance - UNOFFICIAL,
    labelled per row; missing -> "unknown", never guessed.

Output docs/data/event_calendar.json. It feeds the homepage list only: production_use=false,
used_in_decision=false. It deliberately does NOT write market_events.json, whose FOMC/CPI events drive the
options L2 review window (OWN-SYS OS-5-08); adding NFP/PPI/GDP there would silently change risk levels.
Each source fails soft: on failure the previous file's events of that source are kept and marked "cached".
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MARKET_EVENTS = ROOT / "docs" / "data" / "market_events.json"
DATA = ROOT / "docs" / "data.json"
OUT = ROOT / "docs" / "data" / "event_calendar.json"
ET = ZoneInfo("America/New_York")
WINDOW_DAYS = 45
FRED_URL = "https://api.stlouisfed.org/fred/release/dates"
# FRED release ids (St. Louis Fed release calendar)
FRED_RELEASES = {
    "NFP": {"release_id": 50, "title_zh": "美国非农就业报告", "agency": "BLS", "importance": "high",
            "url": "https://www.bls.gov/schedule/news_release/empsit.htm"},
    "PPI": {"release_id": 46, "title_zh": "美国生产者价格指数（PPI）", "agency": "BLS", "importance": "medium",
            "url": "https://www.bls.gov/schedule/news_release/ppi.htm"},
    "GDP": {"release_id": 53, "title_zh": "美国 GDP", "agency": "BEA", "importance": "high",
            "url": "https://www.bea.gov/news/schedule"},
    "PCE": {"release_id": 54, "title_zh": "美国个人收入与支出（PCE 物价）", "agency": "BEA", "importance": "high",
            "url": "https://www.bea.gov/news/schedule"},
    "CPI": {"release_id": 10, "title_zh": "美国 CPI", "agency": "BLS", "importance": "high",
            "url": "https://www.bls.gov/schedule/news_release/cpi.htm"},
}
STANDARD_TIME_ET = (8, 30)


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _et(date_str, hm=STANDARD_TIME_ET):
    d = dt.date.fromisoformat(str(date_str)[:10])
    return dt.datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=ET)


def in_window(when, now, days=WINDOW_DAYS):
    return now - dt.timedelta(days=1) <= when <= now + dt.timedelta(days=days)


# ---------- official FOMC / CPI (already verified by update_market_events.py) ----------
def official_events(doc, now):
    out = []
    for e in (doc or {}).get("events") or []:
        try:
            when = dt.datetime.fromisoformat(str(e.get("datetime")))
        except ValueError:
            continue
        if when.tzinfo is None or not in_window(when, now):
            continue
        kind = str(e.get("type") or "")
        out.append({"key": f"{kind.lower()}_{when.date().isoformat()}", "category": "macro", "type": kind,
                    "title_zh": "FOMC 利率决议" if kind == "FOMC" else "美国 CPI" if kind == "CPI" else e.get("title"),
                    "datetime": when.isoformat(), "date": when.astimezone(ET).date().isoformat(),
                    "time_status": "official", "importance": "high",
                    "source": e.get("source"), "source_url": e.get("source_url")})
    return out


# ---------- FRED official release dates ----------
def fred_get(release_id, api_key, start, timeout=20):
    q = urllib.parse.urlencode({"release_id": release_id, "api_key": api_key, "file_type": "json",
                                "realtime_start": start, "include_release_dates_with_no_data": "true",
                                "sort_order": "asc", "limit": 20})
    req = urllib.request.Request(f"{FRED_URL}?{q}", headers={"User-Agent": "MyAlphaView-EventCalendar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fred_events(kinds, api_key, now, get=fred_get):
    """-> (events, status per kind). Never raises."""
    out, status = [], {}
    if not api_key:
        return out, {k: "unavailable:no_api_key" for k in kinds}
    start = (now - dt.timedelta(days=1)).date().isoformat()
    for kind in kinds:
        meta = FRED_RELEASES[kind]
        try:
            payload = get(meta["release_id"], api_key, start)
            n = 0
            for row in payload.get("release_dates") or []:
                when = _et(row["date"])
                if not in_window(when, now):
                    continue
                n += 1
                out.append({"key": f"{kind.lower()}_{when.date().isoformat()}", "category": "macro", "type": kind,
                            "title_zh": meta["title_zh"], "datetime": when.isoformat(), "date": when.date().isoformat(),
                            "time_status": "official_date_standard_time",
                            "time_note": "日期来自 FRED 官方发布日历；08:30 ET 为该机构的惯例发布时间",
                            "importance": meta["importance"], "source": f"FRED release calendar ({meta['agency']})",
                            "source_url": meta["url"]})
            status[kind] = "fresh" if n else "fresh_none_in_window"
        except Exception as exc:  # noqa: BLE001
            status[kind] = f"unavailable:{type(exc).__name__}"
    return out, status


# ---------- earnings (unofficial) ----------
def yahoo_calendar(symbol):
    import yfinance as yf
    return yf.Ticker(symbol).calendar


def _as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def earnings_events(symbols, now, fetch=yahoo_calendar, pause=0.4):
    out, ok, missing = [], [], []
    for sym in symbols:
        try:
            cal = fetch(sym) or {}
            raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
            dates = sorted({d for d in (_as_date(x) for x in (raw if isinstance(raw, (list, tuple)) else [raw])) if d})
        except Exception:  # noqa: BLE001
            dates = []
        if not dates:
            missing.append(sym)
            continue
        ok.append(sym)
        first = dates[0]
        when = dt.datetime(first.year, first.month, first.day, 0, 0, tzinfo=ET)
        if not in_window(when, now):
            continue
        rng = len(dates) > 1 and dates[-1] != first
        out.append({"key": f"earnings_{sym}_{first.isoformat()}", "category": "earnings", "type": "EARNINGS",
                    "symbol": sym, "title_zh": f"{sym} 财报",
                    "date": first.isoformat(), "date_end": dates[-1].isoformat() if rng else None,
                    "datetime": None,
                    "time_status": "unofficial_estimated_range" if rng else "unofficial_date",
                    "time_note": "Yahoo 非官方日期，盘前/盘后未知；以公司公告为准",
                    "importance": "medium", "source": "Yahoo Finance (yfinance, unofficial)",
                    "source_url": f"https://finance.yahoo.com/quote/{sym}"})
        if pause:
            time.sleep(pause)
    return out, ok, missing


def watchlist(data):
    """Watchlist equities only: ETFs/benchmarks (symbol_registry.ETF) have no earnings."""
    try:
        from symbol_registry import ETF
    except Exception:  # noqa: BLE001
        ETF = set()
    return sorted(k for k in ((data or {}).get("stocks") or {}) if isinstance(k, str) and k.isascii() and k not in ETF)


def merge_with_cache(fresh, status, previous, missing_symbols, now):
    """Keep the previous file's still-upcoming events for a source (or an earnings symbol) that failed this run,
    marked cached - a transient outage never empties the calendar, and nothing is invented."""
    today = (now - dt.timedelta(days=1)).astimezone(ET).date().isoformat()
    keep = []
    for e in (previous or {}).get("events") or []:
        if (e.get("date") or "") < today:
            continue
        failed = (e.get("category") == "earnings" and e.get("symbol") in missing_symbols) or \
                 (e.get("category") == "macro" and e.get("type") in status and not str(status[e["type"]]).startswith("fresh"))
        if failed:
            keep.append(dict(e, cached=True))
    return fresh + keep


def build(market_events, data, previous, api_key, now, fred_get_fn=fred_get, earnings_fetch=yahoo_calendar, pause=0.4):
    events = official_events(market_events, now)
    official_kinds = {e["type"] for e in events}
    cpi_cached = ((market_events or {}).get("source_status") or {}).get("CPI") != "fresh"
    kinds = ["NFP", "PPI", "GDP", "PCE"] + (["CPI"] if cpi_cached else [])
    fred, fred_status = fred_events(kinds, api_key, now, get=fred_get_fn)
    if "CPI" in official_kinds:  # official BLS/Fed rows win; FRED CPI only fills a gap
        fred = [e for e in fred if e["type"] != "CPI" or e["date"] not in {x["date"] for x in events if x["type"] == "CPI"}]
    syms = watchlist(data)
    earn, ok, missing = earnings_events(syms, now, fetch=earnings_fetch, pause=pause)
    earn_status = "fresh" if ok else ("unavailable" if syms else "no_watchlist")
    status = dict(fred_status, EARNINGS=earn_status,
                  FOMC_CPI=(market_events or {}).get("source_status") or "unavailable")
    events = merge_with_cache(events + fred + earn, fred_status, previous, set(missing), now)
    seen, uniq = set(), []
    for e in sorted(events, key=lambda x: (x.get("date") or "", x.get("datetime") or "", x.get("key"))):
        if e["key"] in seen:
            continue
        seen.add(e["key"])
        uniq.append(e)
    return {
        "version": 1, "generated_at": now.astimezone(dt.timezone.utc).isoformat(), "window_days": WINDOW_DAYS,
        "policy": "display_only", "production_use": False, "used_in_decision": False,
        "note": "宏观：FOMC/CPI 来自美联储/BLS 官方；非农/PPI/GDP/PCE 日期来自 FRED 官方发布日历。财报：Yahoo 非官方日期，以公司公告为准。",
        "source_status": status,
        "earnings_coverage": {"watchlist": len(syms), "with_date": len(ok), "unknown": missing},
        "events": uniq,
    }


def main():
    now = dt.datetime.now(dt.timezone.utc)
    previous = load(OUT, {})
    out = build(load(MARKET_EVENTS, {}), load(DATA, {}), previous, os.getenv("FRED_API_KEY", "").strip(), now)
    if not out["events"] and previous.get("events"):
        print("::warning title=Event calendar::no events from any source; keeping the previous file")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"::notice title=Event calendar::EVENT_CALENDAR events={len(out['events'])} status={out['source_status']} "
          f"earnings={out['earnings_coverage']['with_date']}/{out['earnings_coverage']['watchlist']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
