#!/usr/bin/env python3
"""V6.11 Investment Watch: gold staged-buying monitor + monthly ETF DCA reminders.

Research and reminders only. Never places, closes or rolls orders.

Public output (docs/research/investment_actions_status.json) carries market
research only: XAU/USD quote + provenance + freshness, stage bands, rule checks,
state (WAIT/WATCH/BUY/PAUSE/REVIEW/DATA_STALE), the DCA *calendar* (dates only)
and an alert de-duplication state. Personal amounts (gold budget, monthly DCA
amount, executions) live only in private Supabase tables and are read here with
the service credentials solely to compose private Telegram reminders.

Gold signals are appended as state entries to research/archive/gold_signal_journal.jsonl
(live forward captures only) and matured into 20/60/120-session outcomes.
"""
from __future__ import annotations

import csv, hashlib, io, json, os, sys, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar  # noqa: E402

CONFIG = ROOT / "config" / "gold_etf_long_term_watch.json"
DCA_CONFIG = ROOT / "config" / "monthly_dca_plan.json"
OUT = ROOT / "docs" / "research" / "investment_actions_status.json"
JOURNAL = ROOT / "research" / "archive" / "gold_signal_journal.jsonl"
OUTCOMES = ROOT / "research" / "archive" / "gold_signal_outcomes.json"
OZ_GRAMS = 31.1034768
ET = ZoneInfo("America/New_York")
SH = ZoneInfo("Asia/Shanghai")
UA = {"User-Agent": "Mozilla/5.0 MyAlpha-Investment-Watch", "Accept": "application/json,text/csv,*/*"}
VERSION = "6.11-p1"
HORIZONS = (20, 60, 120)


# --------------------------------------------------------------------------- utils

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def parse_dt(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def rnd(v, n=2):
    return None if v is None else round(float(v), n)


def cny_per_gram(usd_oz, usdcny):
    if not usd_oz or not usdcny:
        return None
    return float(usd_oz) * float(usdcny) / OZ_GRAMS


# ------------------------------------------------------------------ gold session

def gold_market_open(at):
    """COMEX/OTC gold: Sun 18:00 ET → Fri 17:00 ET, daily 17:00–18:00 ET break.

    Holidays are not modelled; a holiday shows as an ageing quote, which the
    freshness classifier reports as DELAYED/STALE rather than as live."""
    et = at.astimezone(ET)
    wd, minute = et.weekday(), et.hour * 60 + et.minute
    if wd == 5:
        return False
    if wd == 6:
        return minute >= 18 * 60
    if wd == 4 and minute >= 17 * 60:
        return False
    return not (17 * 60 <= minute < 18 * 60)


def last_gold_close(at):
    """Most recent 17:00 ET close at or before `at`."""
    et = at.astimezone(ET)
    cand = et.replace(hour=17, minute=0, second=0, microsecond=0)
    if cand > et:
        cand -= timedelta(days=1)
    while cand.weekday() == 5 or cand.weekday() == 6:  # no close on Sat/Sun
        cand -= timedelta(days=1)
    return cand.astimezone(timezone.utc)


def quote_freshness(quote_at, at, realtime_source, cfg):
    """LIVE / DELAYED / CLOSED / STALE. Old data never masquerades as live."""
    fr = cfg.get("freshness", {})
    if not quote_at:
        return "STALE", None
    age_min = (at - quote_at).total_seconds() / 60
    if age_min < -5:
        return "STALE", age_min
    if gold_market_open(at):
        if age_min <= fr.get("live_max_age_minutes", 20):
            return ("LIVE" if realtime_source else "DELAYED"), age_min
        if age_min <= fr.get("delayed_max_age_minutes", 90):
            return "DELAYED", age_min
        return "STALE", age_min
    close = last_gold_close(at)
    if quote_at >= close - timedelta(minutes=fr.get("delayed_max_age_minutes", 90)):
        return "CLOSED", age_min
    return "STALE", age_min


# ------------------------------------------------------------------ pure rules

def stage_for(price, cfg):
    for st in cfg["stages"]:
        if st["min"] <= price < st["max"] or (st["stage"] == 1 and price == st["max"]):
            return st
    return None


def zone_for(price, cfg):
    core = cfg["core_watch_zone_usd_oz"]
    lo = min(s["min"] for s in cfg["stages"])
    hi = max(s["max"] for s in cfg["stages"])
    if price is None:
        return "unknown"
    if price > cfg["rules"]["breakout_review"]["above"]:
        return "breakout"
    if price > hi:
        return "above_plan"
    if price < lo:
        return "below_plan"
    if core["min"] <= price <= core["max"]:
        return "core_watch"
    return "deep_plan"


def pct_change_n(values, n):
    vals = [v for v in values if v is not None]
    if len(vals) <= n:
        return None
    a, b = vals[-1 - n], vals[-1]
    return (b / a - 1) * 100 if a else None


def diff_n(values, n):
    vals = [v for v in values if v is not None]
    if len(vals) <= n:
        return None
    return vals[-1] - vals[-1 - n]


def weekly_closes(daily):
    """Last close of each ISO week from daily rows [{date, close}]."""
    weeks = {}
    for r in daily:
        d = date.fromisoformat(r["date"])
        weeks[d.isocalendar()[:2]] = r
    return [weeks[k] for k in sorted(weeks)]


def pause_checks(daily, real_yield, dxy, cfg):
    p = cfg["rules"]["pause"]
    closes = [r["close"] for r in daily]
    n = p["close_below_sessions"]
    c1 = None if len(closes) < n else all(c < p["close_below"] for c in closes[-n:])
    ry = diff_n([r["value"] for r in real_yield], 5)
    c2 = None if ry is None else ry * 100 >= p["real_yield_rise_bp_5d"]
    dx = pct_change_n([r["close"] for r in dxy], 5)
    c3 = None if dx is None else dx > p["dxy_rise_pct_5d"]
    checks = [
        {"id": "gold_close_below", "met": c1, "value": closes[-n:] if len(closes) >= n else None,
         "rule": f"连续{n}个交易日收在 ${p['close_below']:,} 以下"},
        {"id": "real_yield_rise", "met": c2, "value_bp": None if ry is None else round(ry * 100, 1),
         "rule": f"10Y 实际收益率 5 日上升 ≥ {p['real_yield_rise_bp_5d']}bp"},
        {"id": "dxy_rise", "met": c3, "value_pct": rnd(dx, 2),
         "rule": f"DXY 5 日涨幅 > {p['dxy_rise_pct_5d']}%"},
    ]
    met = sum(1 for c in checks if c["met"] is True)
    unknown = sum(1 for c in checks if c["met"] is None)
    return {
        "checks": checks,
        "met": met,
        "unknown": unknown,
        "pause": met >= p["min_conditions"],
        # Could the unknown inputs still flip the verdict to PAUSE?
        "complete": met >= p["min_conditions"] or met + unknown < p["min_conditions"],
        "ry_change_bp_5d": None if ry is None else round(ry * 100, 1),
        "dxy_change_pct_5d": rnd(dx, 2),
    }


def deep_review_check(daily, real_yield, cfg):
    r = cfg["rules"]["deep_review"]
    weeks = weekly_closes(daily)
    last = weeks[-r["weeks"]:] if len(weeks) >= r["weeks"] else []
    below = bool(last) and all(w["close"] < r["weekly_close_below"] for w in last)
    ry = diff_n([x["value"] for x in real_yield], 5)
    worsening = ry is not None and ry > 0
    return {
        "triggered": below and (worsening or not r.get("requires_real_yield_worsening", True)),
        "weekly_closes_below": below,
        "real_yield_worsening": worsening,
        "etf_flows": "unavailable_free_source",
        "weeks": [{"date": w["date"], "close": rnd(w["close"])} for w in last],
    }


def confirmation(daily):
    """Stabilisation + short trend from completed daily bars."""
    if len(daily) < 6:
        return {"ok": None, "stabilized": None, "trend": None, "detail": "日线样本不足"}
    a, b, c = daily[-3], daily[-2], daily[-1]
    lows_ok = all(x.get("low") is not None for x in (a, b, c))
    no_lower_low = lows_ok and b["low"] >= a["low"] and c["low"] >= b["low"]
    reversal = b.get("high") is not None and c["close"] > b["high"]
    stabilized = bool(no_lower_low or reversal)
    sma5 = sum(x["close"] for x in daily[-5:]) / 5
    trend = c["close"] >= sma5
    why = []
    why.append("两日未创新低" if no_lower_low else ("收盘突破前日高点" if reversal else "仍在创新低"))
    why.append(f"收盘 {c['close']:,.0f} {'≥' if trend else '<'} 5日均线 {sma5:,.0f}")
    return {"ok": stabilized and trend, "stabilized": stabilized, "trend": trend,
            "sma5": rnd(sma5), "detail": "；".join(why), "as_of": c["date"]}


def decide(price, freshness, daily, real_yield, dxy, cfg, daily_fresh=True, macro_fresh=True):
    """Return the gold decision. Precedence:
    DATA_STALE > DEEP_REVIEW > PAUSE > BREAKOUT_REVIEW > below-plan REVIEW > BUY > WATCH > WAIT."""
    zone = zone_for(price, cfg)
    stage = stage_for(price, cfg) if price is not None else None
    pc = pause_checks(daily, real_yield, dxy, cfg)
    dr = deep_review_check(daily, real_yield, cfg)
    conf = confirmation(daily)
    reasons = []
    base = {"zone": zone, "stage": stage["stage"] if stage else None,
            "stage_budget_pct": stage["budget_pct"] if stage else None,
            "pause": pc, "deep_review": dr, "confirmation": conf}

    if price is None or freshness == "STALE":
        return {**base, "state": "DATA_STALE", "reasons": ["黄金报价过期或缺失：停止生成新的 BUY 建议"]}
    if dr["triggered"]:
        return {**base, "state": "REVIEW", "review_kind": "DEEP_REVIEW",
                "reasons": ["连续两周周收盘低于 $3,650，且实际利率恶化：深度复核，暂停按档买入"]}
    if pc["pause"]:
        hit = [c["rule"] for c in pc["checks"] if c["met"]]
        return {**base, "state": "PAUSE", "reasons": ["风险升高，暂停新买入：" + "；".join(hit)]}
    if zone == "breakout":
        return {**base, "state": "REVIEW", "review_kind": "BREAKOUT_REVIEW",
                "reasons": [f"突破 ${cfg['rules']['breakout_review']['above']:,}：趋势复核，不追高"]}
    if zone == "below_plan":
        return {**base, "state": "REVIEW", "review_kind": "BELOW_PLAN",
                "reasons": ["跌破全部计划档位：不机械越跌越买，等待复核"]}
    if zone in ("above_plan",):
        nxt = cfg["core_watch_zone_usd_oz"]
        return {**base, "state": "WAIT",
                "reasons": [f"高于观察区；等待 ${nxt['min']:,}–{nxt['max']:,}"]}

    # In a plan band → WATCH unless every BUY condition is confirmed.
    blockers = []
    if freshness not in ("LIVE", "DELAYED"):
        blockers.append("市场休市/报价非盘中，不生成新 BUY")
    if not daily_fresh:
        blockers.append("黄金日线过期")
    if not macro_fresh or not pc["complete"]:
        blockers.append("宏观风险数据缺失（DXY/实际利率），无法排除 PAUSE")
    if pc["met"] >= 1:
        blockers.append("宏观/价格风险已出现 1 项，等待复核")
    if conf["ok"] is not True:
        blockers.append("止跌/趋势未确认：" + conf.get("detail", ""))
    if blockers:
        return {**base, "state": "WATCH", "blockers": blockers,
                "reasons": [f"已进入第{stage['stage']}档 {stage['label_zh']}；BUY 条件未齐备"]}
    return {**base, "state": "BUY",
            "reasons": [f"第{stage['stage']}档条件确认：{conf['detail']}；DXY/实际利率未恶化"]}


def next_band(stage_no, cfg):
    for st in cfg["stages"]:
        if stage_no is None and st["stage"] == 1:
            return st
        if stage_no is not None and st["stage"] == stage_no + 1:
            return st
    return None


def alert_events(prev, decision, price, cfg):
    """De-duplicated gold alert events + next alert state (pure)."""
    prev = dict(prev or {})
    st = {
        "armed_watch": prev.get("armed_watch", True),
        "armed_breakout": prev.get("armed_breakout", True),
        "buy_sent_stages": list(prev.get("buy_sent_stages", [])),
        "last_state": prev.get("last_state"),
        "last_review_kind": prev.get("last_review_kind"),
    }
    events = []
    state, zone = decision["state"], decision["zone"]
    if state == "DATA_STALE" or price is None:
        return events, st  # never alert on stale data; keep previous arming
    top = max(s["max"] for s in cfg["stages"])
    hyst = cfg["rules"].get("rearm_hysteresis_usd", 20)
    in_plan = zone in ("core_watch", "deep_plan")
    if price > top + hyst:
        st["armed_watch"] = True
        st["buy_sent_stages"] = []
    if in_plan and st["armed_watch"]:
        events.append("ENTER_WATCH_ZONE")
        st["armed_watch"] = False
    if state == "BUY" and decision.get("stage") not in st["buy_sent_stages"]:
        events.append("BUY_CONDITIONAL")
        st["buy_sent_stages"].append(decision.get("stage"))
    if state == "PAUSE" and st["last_state"] != "PAUSE":
        events.append("PAUSE_BUYING")
        st["buy_sent_stages"] = []  # after a pause, a new BUY is a material change
    kind = decision.get("review_kind")
    if kind == "DEEP_REVIEW" and st["last_review_kind"] != "DEEP_REVIEW":
        events.append("DEEP_REVIEW")
    br = cfg["rules"]["breakout_review"]
    if price < br["rearm_below"]:
        st["armed_breakout"] = True
    if kind == "BREAKOUT_REVIEW" and st["armed_breakout"]:
        events.append("BREAKOUT_REVIEW")
        st["armed_breakout"] = False
    st["last_state"] = state
    st["last_review_kind"] = kind
    return events, st


# --------------------------------------------------------------- year stats / fx

def fx_on(fx_rows, d):
    """USD/CNY close for date d (latest on or before d) — never today's rate for history."""
    best = None
    for r in fx_rows:
        if r["date"] <= d:
            best = r
    return best


def year_stats(daily, fx_rows, year, cfg, price=None, price_fx=None, basis="spot"):
    """Year high/low. Verified provenance values win over estimates; a futures-derived spot
    estimate is only used for the period after the verified data and is labelled as such."""
    rows = [r for r in daily if r["date"].startswith(str(year))]
    prov = cfg.get("provenance", {})
    ph, pl = prov.get("spot_high_2026"), prov.get("verified_spot_low_h1_2026")
    estimate = basis != "spot"
    out = {"year": year, "basis": basis if rows else None, "high": None, "low": None, "low_estimate_after_verified": None}
    if rows:
        hi = max(rows, key=lambda r: r.get("high") or r["close"])
        lo = min(rows, key=lambda r: r.get("low") or r["close"])
        out["coverage"] = {"from": rows[0]["date"], "to": rows[-1]["date"], "sessions": len(rows)}
        if not estimate:
            out["high"] = {"value": rnd(hi.get("high") or hi["close"]), "date": hi["date"]}
            out["low"] = {"value": rnd(lo.get("low") or lo["close"]), "date": lo["date"]}
    if ph and (out["high"] is None or ph["value"] >= (out["high"]["value"] or 0)):
        out["high"] = {"value": ph["value"], "date": ph["date"], "source": ph["source"], "intraday": True, "verified": True}
    if pl and (out["low"] is None or estimate or pl["value"] <= (out["low"]["value"] or 1e9)):
        out["low"] = {"value": pl["value"], "date": pl["date"], "source": pl["source"], "intraday": True, "verified": True}
    if estimate and rows and pl:
        later = [r for r in rows if r["date"] > pl["date"]]
        if later:
            lo2 = min(later, key=lambda r: r.get("low") or r["close"])
            out["low_estimate_after_verified"] = {"value": rnd(lo2.get("low") or lo2["close"]), "date": lo2["date"],
                                                  "basis": basis, "note": "期货基差估算，未经核实"}
    out["low_is_full_year_confirmed"] = False  # year not complete; never label as 全年最低
    for key in ("high", "low", "low_estimate_after_verified"):
        x = out.get(key)
        if x:
            fx = fx_on(fx_rows, x["date"])
            x["usdcny"] = rnd(fx["close"], 4) if fx else None
            x["usdcny_date"] = fx["date"] if fx else None
            x["cny_per_gram"] = rnd(cny_per_gram(x["value"], fx["close"])) if fx else None
    if price and out.get("high"):
        out["drawdown_from_high_pct"] = rnd((price / out["high"]["value"] - 1) * 100)
    if price and out.get("low"):
        out["above_low_pct"] = rnd((price / out["low"]["value"] - 1) * 100)
    return out


# ----------------------------------------------------------------------- fetchers

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def yahoo_chart(symbol, rng="1y", interval="1d"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?range={rng}&interval={interval}&includePrePost=false")
    payload = json.loads(http_get(url))
    res = payload["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    rows = []
    tz = ZoneInfo(meta.get("exchangeTimezoneName") or "America/New_York")
    for i, t in enumerate(ts):
        c = (q.get("close") or [None])[i] if i < len(q.get("close") or []) else None
        if c is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(t, tz=timezone.utc).astimezone(tz).date().isoformat(),
            "close": float(c),
            "high": (q.get("high") or [None] * len(ts))[i],
            "low": (q.get("low") or [None] * len(ts))[i],
        })
    dedup = {}
    for r in rows:
        dedup[r["date"]] = r
    return meta, [dedup[k] for k in sorted(dedup)]


def fetch_spot_live():
    """Real-time spot first (gold-api.com, free/no key); Yahoo COMEX futures as a labelled proxy."""
    errors = []
    try:
        doc = json.loads(http_get("https://api.gold-api.com/price/XAU", 10))
        price = float(doc["price"])
        at = parse_dt(doc.get("updatedAt")) or now_utc()
        return {"ok": True, "price": price, "as_of": iso(at), "source": "gold-api.com 现货",
                "basis": "spot", "realtime": True}
    except Exception as e:
        errors.append(f"gold-api:{type(e).__name__}")
    try:
        meta, _ = yahoo_chart("GC=F", "5d", "1d")
        price = float(meta["regularMarketPrice"])
        at = parse_dt(int(meta.get("regularMarketTime")))
        return {"ok": True, "price": price, "as_of": iso(at), "source": "Yahoo COMEX期货(GC=F)代理",
                "basis": "futures_proxy", "realtime": False, "fallback_errors": errors}
    except Exception as e:
        errors.append(f"yahoo-gc:{type(e).__name__}")
    return {"ok": False, "errors": errors}


def fetch_spot_daily():
    """Daily XAU/USD bars for rules + year stats. Spot first; futures only as labelled proxy."""
    errors = []
    try:
        text = http_get("https://stooq.com/q/d/l/?s=xauusd&i=d", 15)
        rows = []
        for r in csv.DictReader(io.StringIO(text)):
            try:
                rows.append({"date": r["Date"], "close": float(r["Close"]),
                             "high": float(r["High"]), "low": float(r["Low"])})
            except Exception:
                continue
        rows = [r for r in rows if r["date"] >= f"{date.today().year - 1}-01-01"]
        if len(rows) > 30:
            return {"ok": True, "rows": rows, "source": "Stooq XAUUSD 现货日线", "basis": "spot"}
        errors.append("stooq:empty")
    except Exception as e:
        errors.append(f"stooq:{type(e).__name__}")
    for sym, basis, label in (("XAUUSD=X", "spot", "Yahoo XAUUSD 现货日线"),
                              ("GC=F", "futures_proxy", "Yahoo COMEX期货日线(代理)")):
        try:
            _, rows = yahoo_chart(sym, "2y", "1d")
            rows = [r for r in rows if r["date"] >= f"{date.today().year - 1}-01-01"]
            if len(rows) > 30:
                return {"ok": True, "rows": rows, "source": label, "basis": basis, "fallback_errors": errors}
            errors.append(f"{sym}:empty")
        except Exception as e:
            errors.append(f"{sym}:{type(e).__name__}")
    return {"ok": False, "rows": [], "errors": errors}


def basis_adjust(daily, live, futures_now=None):
    """Free spot daily bars are unavailable on runners (Stooq needs a key, Yahoo XAUUSD=X is gone).
    When only COMEX futures bars exist, shift them by the *measured* futures−spot basis so level
    rules (e.g. closes below $4,000) are evaluated on a spot estimate. Shape rules (no lower low,
    close vs SMA5) are unaffected by a constant shift. Labelled; never presented as true spot."""
    if daily.get("basis") != "futures_proxy" or not daily.get("rows") or live.get("basis") != "spot":
        return daily
    try:
        fut = futures_now if futures_now is not None else float(yahoo_chart("GC=F", "5d", "1d")[0]["regularMarketPrice"])
    except Exception as e:
        return {**daily, "basis_adjust_error": type(e).__name__}
    basis = fut - float(live["price"])
    if abs(basis) > 150:  # implausible (contract roll / bad print): keep raw proxy, label it
        return {**daily, "basis_adjust_error": f"implausible_basis_{basis:.0f}"}
    rows = [{**r, "close": r["close"] - basis,
             "high": (r["high"] - basis) if r.get("high") is not None else None,
             "low": (r["low"] - basis) if r.get("low") is not None else None} for r in daily["rows"]]
    return {**daily, "rows": rows, "basis": "spot_estimate_from_futures", "futures_spot_basis": round(basis, 2),
            "source": f"COMEX期货日线 − 实时基差 {basis:+.1f}（现货估算）"}


def fetch_fred(series):
    text = http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", 20)
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        d = r.get("observation_date") or r.get("DATE")
        v = r.get(series)
        try:
            rows.append({"date": d, "value": float(v)})
        except Exception:
            continue
    return rows[-260:]


def fetch_etf_quotes(symbols):
    out = {}
    for sym, ysym in symbols:
        try:
            meta, _ = yahoo_chart(ysym, "5d", "1d")
            out[sym] = {"price": rnd(meta.get("regularMarketPrice"), 2), "currency": meta.get("currency"),
                        "as_of": iso(parse_dt(int(meta.get("regularMarketTime") or 0))),
                        "source": f"Yahoo {ysym}", "delayed": True}
        except Exception as e:
            out[sym] = {"error": type(e).__name__, "source": f"Yahoo {ysym}"}
    return out


def collect():
    data = {"errors": {}}
    data["live"] = fetch_spot_live()
    data["daily"] = basis_adjust(fetch_spot_daily(), data["live"])
    try:
        data["real_yield"] = {"ok": True, "rows": fetch_fred("DFII10"), "source": "FRED DFII10 (10Y TIPS)"}
    except Exception as e:
        data["real_yield"] = {"ok": False, "rows": [], "error": type(e).__name__}
    try:
        _, rows = yahoo_chart("DX-Y.NYB", "6mo", "1d")
        data["dxy"] = {"ok": True, "rows": rows, "source": "Yahoo DX-Y.NYB"}
    except Exception as e:
        data["dxy"] = {"ok": False, "rows": [], "error": type(e).__name__}
    try:
        meta, rows = yahoo_chart("CNY=X", "2y", "1d")
        data["fx"] = {"ok": True, "rows": rows, "live": meta.get("regularMarketPrice"),
                      "live_at": iso(parse_dt(int(meta.get("regularMarketTime") or 0))), "source": "Yahoo CNY=X"}
    except Exception as e:
        data["fx"] = {"ok": False, "rows": [], "error": type(e).__name__}
    data["etf"] = fetch_etf_quotes([("GLDM", "GLDM"), ("IAU", "IAU"), ("GLD", "GLD"), ("SGLN", "SGLN.L")])
    data["dca_quotes"] = fetch_etf_quotes([(s, s) for s in ("QQQM", "QLD", "VGT")])
    return data


# ------------------------------------------------------------------------- DCA

def dca_window(year, month, plan):
    """Reminder window in Asia/Shanghai calendar dates, rolled to US trading sessions."""
    start = date(year, month, int(plan.get("window_start_day", 7)))
    end = date(year, month, int(plan.get("window_end_day", 10)))
    due = start if trading_calendar.is_session(start) else trading_calendar.next_session(start)
    last = end if trading_calendar.is_session(end) else trading_calendar.next_session(end)
    if last < due:
        last = due
    return {"month": f"{year:04d}-{month:02d}", "nominal": f"{start.isoformat()}~{end.isoformat()}",
            "due_date": due.isoformat(), "window_end": last.isoformat(),
            "rolled": due != start or last != end}


def dca_calendar(today_sh, plan, months=3):
    out, y, m = [], today_sh.year, today_sh.month
    for _ in range(months):
        out.append(dca_window(y, m, plan))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def dca_phase(today_sh, window):
    d = today_sh.isoformat()
    if d < window["due_date"]:
        return "upcoming"
    if d <= window["window_end"]:
        return "due" if d == window["due_date"] else "in_window"
    return "after_window"


def dca_events(plan_row, window, today_sh):
    """Private DCA reminder events for one monthly plan (pure, de-duplicated)."""
    sent = set(plan_row.get("notified_events") or [])
    status = plan_row.get("status") or "pending"
    phase = dca_phase(today_sh, window)
    session = trading_calendar.is_session(today_sh)
    ev = []
    if status == "completed" and "DCA_COMPLETED" not in sent:
        ev.append("DCA_COMPLETED")
    elif status == "skipped" and "DCA_SKIPPED" not in sent:
        ev.append("DCA_SKIPPED")
    elif status == "partial" and "DCA_PARTIAL" not in sent:
        ev.append("DCA_PARTIAL")
    elif status in ("pending", "partial") and phase in ("due", "in_window") and session:
        if "DCA_DUE" not in sent:
            ev.append("DCA_DUE")
        elif f"DCA_PENDING:{today_sh.isoformat()}" not in sent:
            ev.append(f"DCA_PENDING:{today_sh.isoformat()}")
    return ev


def dca_split(amount_cny, weights):
    total = sum(float(v) for v in weights.values()) or 1.0
    rows, acc = [], 0.0
    items = list(weights.items())
    for i, (sym, w) in enumerate(items):
        amt = round(float(amount_cny) * float(w) / total, 2) if i < len(items) - 1 else round(float(amount_cny) - acc, 2)
        acc += amt
        rows.append({"symbol": sym, "weight": float(w) / total, "amount_cny": amt})
    return rows


# --------------------------------------------------------------- journal / outcomes

def journal_rows(path=JOURNAL):
    rows = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def journal_entry(decision, live, at, cfg):
    key = f"{decision['state']}|{decision.get('stage')}|{decision.get('review_kind')}"
    sid = hashlib.sha256(f"{key}|{iso(at)}".encode()).hexdigest()[:16]
    return {
        "signal_id": sid, "state_key": key, "recorded_at": iso(at),
        "state": decision["state"], "stage": decision.get("stage"), "zone": decision["zone"],
        "review_kind": decision.get("review_kind"),
        "price": rnd(live.get("price")), "price_basis": live.get("basis"),
        "quote_source": live.get("source"), "quote_as_of": live.get("as_of"),
        "rules": decision.get("reasons", []) + decision.get("blockers", []),
        "config_version": cfg.get("schema_version"),
        "capture_mode": "live_forward", "forward_evidence_eligible": True,
        "user_execution": "private_ledger_only",
    }


def should_journal(prev_rows, decision):
    if decision["state"] == "DATA_STALE":
        return False
    key = f"{decision['state']}|{decision.get('stage')}|{decision.get('review_kind')}"
    return not prev_rows or prev_rows[-1].get("state_key") != key


def evaluate_outcomes(rows, daily):
    """Forward spot returns after 20/60/120 completed sessions (only when mature)."""
    dates = [r["date"] for r in daily]
    closes = {r["date"]: r["close"] for r in daily}
    out = []
    for s in rows:
        d0 = (s.get("recorded_at") or "")[:10]
        idx = next((i for i, d in enumerate(dates) if d >= d0), None)
        rec = {"signal_id": s["signal_id"], "state": s["state"], "stage": s.get("stage"), "price": s.get("price")}
        for h in HORIZONS:
            if idx is not None and idx + h < len(dates) and s.get("price"):
                c = closes[dates[idx + h]]
                rec[f"ret_{h}d_pct"] = rnd((c / s["price"] - 1) * 100)
                rec[f"mature_{h}d"] = True
            else:
                rec[f"mature_{h}d"] = False
        out.append(rec)
    return out


# --------------------------------------------------------------------- telegram

def send_telegram(text):
    try:
        import server_action_engine as sa
        return sa.send_telegram(text)
    except Exception as e:
        return f"failed:{type(e).__name__}"


def private_gold_context():
    """Owner budget + executed stages via service role (private; only used inside Telegram text)."""
    try:
        st = sb_request("GET", "investment_plan_settings?select=gold_budget_usd") or []
        ex = sb_request("GET", "investment_executions?select=gold_stage,shares,price_usd,fee_usd&program=eq.gold") or []
    except Exception:
        return None
    budget = next((float(x["gold_budget_usd"]) for x in st if x.get("gold_budget_usd") is not None), None)
    spent = sum(float(x["shares"]) * float(x["price_usd"]) + float(x.get("fee_usd") or 0) for x in ex)
    return {"budget": budget, "spent": spent, "stages": sorted({int(x["gold_stage"]) for x in ex if x.get("gold_stage")})}


def gold_message(event, decision, live, cfg, etf, private=None):
    p = live.get("price")
    head = {
        "ENTER_WATCH_ZONE": "⚠ 黄金已进入观察区",
        "BUY_CONDITIONAL": "🟡 黄金分阶段买入条件确认",
        "PAUSE_BUYING": "⛔ 黄金风险升高 · 暂停新买入",
        "DEEP_REVIEW": "🔴 黄金深度调整 · 深度复核",
        "BREAKOUT_REVIEW": "📈 黄金突破 · 趋势复核",
    }[event]
    lines = [f"MyAlpha｜{head}", f"XAU/USD ${p:,.2f}（{live.get('source')} · {live.get('as_of')}）"]
    if decision.get("stage"):
        lines.append(f"档位：第{decision['stage']}档 · 计划预算 {decision['stage_budget_pct']}%")
    lines += [f"判断：{r}" for r in decision.get("reasons", [])[:2]]
    if event == "BUY_CONDITIONAL":
        q = [f"{k} {v['price']}{v.get('currency') or ''}" for k, v in (etf or {}).items() if v.get("price")]
        if q:
            lines.append("ETF：" + " / ".join(q[:4]))
        nb = next_band(decision.get("stage"), cfg)
        if nb:
            lines.append(f"下一档观察：${nb['max']:,}–{nb['min']:,}")
        stage = decision.get("stage")
        if private and private.get("budget"):
            amt = private["budget"] * decision["stage_budget_pct"] / 100
            lines.append(f"建议金额 ≈ ${amt:,.0f}（黄金预算 ${private['budget']:,.0f} × {decision['stage_budget_pct']}%）")
            if stage in private.get("stages", []):
                lines.append("注意：本档已记录执行，不重复扣减预算。")
        else:
            lines.append("未设置黄金预算：不输出建议金额（网站私有设置中填写）。")
        lines.append("仅提醒，不自动下单。")
    return "\n".join(lines)


def dca_message(event, plan_row, window, split):
    base = event.split(":")[0]
    head = {"DCA_DUE": "📅 本月定投提醒", "DCA_PENDING": "⏳ 本月定投尚未完成",
            "DCA_PARTIAL": "◐ 本月定投部分完成", "DCA_COMPLETED": "✅ 本月定投已完成",
            "DCA_SKIPPED": "⏭ 本月定投已跳过"}[base]
    amt = plan_row.get("amount_cny")
    lines = [f"MyAlpha｜{head}（{window['month']}）"]
    if base in ("DCA_DUE", "DCA_PENDING", "DCA_PARTIAL") and amt:
        lines.append(f"计划 ¥{float(amt):,.0f}：" + " / ".join(f"{x['symbol']} ¥{x['amount_cny']:,.0f}" for x in split))
        lines.append(f"窗口：{window['due_date']} ~ {window['window_end']}（Asia/Shanghai，按美股交易日顺延）")
        lines.append("在网站标记 已完成 / 部分完成 / 跳过 后停止本月提醒。")
    return "\n".join(lines)


# ---------------------------------------------------------------- supabase (private)

def sb_request(method, path, body=None, prefer=None):
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not base or not key:
        return None
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "User-Agent": "MyAlpha-Investment-Watch"}
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(f"{base.rstrip('/')}/rest/v1/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode() or "null"
        return json.loads(raw)


def run_dca(today_sh, dca_cfg):
    """Returns aggregate-only status (no amounts) for annotations."""
    try:
        settings = sb_request("GET", "investment_plan_settings?select=*")
    except Exception as e:
        return {"dca": "migration_missing_or_error", "error": type(e).__name__}
    if settings is None:
        return {"dca": "not_configured"}
    summary = {"dca": "ok", "users": len(settings), "events": [], "delivery": []}
    win = dca_window(today_sh.year, today_sh.month, dca_cfg)
    month_key = f"{win['month']}-01"
    for s in settings:
        uid = s.get("user_id")
        amount, weights = s.get("dca_monthly_cny"), s.get("dca_weights") or {}
        if not uid or not amount or not weights or s.get("dca_enabled") is False:
            continue
        sb_request("POST", "dca_monthly_plans?on_conflict=user_id,plan_month",
                   [{"user_id": uid, "plan_month": month_key, "amount_cny": amount, "weights": weights,
                     "due_date": win["due_date"], "window_end": win["window_end"]}],
                   prefer="resolution=ignore-duplicates,return=minimal")
        rows = sb_request("GET", f"dca_monthly_plans?select=*&user_id=eq.{uid}&plan_month=eq.{month_key}") or []
        if not rows:
            continue
        plan = rows[0]
        events = dca_events(plan, win, today_sh)
        sent = list(plan.get("notified_events") or [])
        for ev in events:
            msg = dca_message(ev, plan, win, dca_split(plan["amount_cny"], plan.get("weights") or weights))
            res = send_telegram(msg)
            summary["events"].append(ev.split(":")[0])
            summary["delivery"].append(res)
            if res == "sent":
                sent.append(ev)
        if sent != list(plan.get("notified_events") or []):
            sb_request("PATCH", f"dca_monthly_plans?id=eq.{plan['id']}", {"notified_events": sent},
                       prefer="return=minimal")
    return summary


# --------------------------------------------------------------------------- main

def build_status(data, cfg, dca_cfg, prev, at):
    live = data["live"] if data["live"].get("ok") else {}
    price = live.get("price")
    q_at = parse_dt(live.get("as_of"))
    fresh, age = quote_freshness(q_at, at, live.get("realtime", False), cfg)
    daily = data["daily"].get("rows", [])
    ry = data["real_yield"].get("rows", [])
    dxy = data["dxy"].get("rows", [])
    fr = cfg["freshness"]
    today = at.date()

    def recent(rows, days, key="date"):
        return bool(rows) and (today - date.fromisoformat(rows[-1][key])).days <= days

    daily_fresh = recent(daily, fr["daily_max_age_days"])
    macro_fresh = recent(ry, fr["real_yield_max_age_days"]) and recent(dxy, fr["daily_max_age_days"])
    # Completed bars only: drop today's partial bar while the market is still open.
    completed = [r for r in daily if r["date"] < at.astimezone(ET).date().isoformat()] if gold_market_open(at) else daily
    decision = decide(price, fresh, completed, ry, dxy, cfg, daily_fresh=daily_fresh, macro_fresh=macro_fresh)
    if live.get("basis") == "futures_proxy" and decision["state"] == "BUY":
        decision["state"] = "WATCH"
        decision.setdefault("blockers", []).append("仅有期货代理报价，非现货：不生成 BUY")
    if data["daily"].get("basis") == "futures_proxy" and decision["state"] == "BUY":
        decision["state"] = "WATCH"
        decision.setdefault("blockers", []).append("日线仅有未校正的期货代理：不生成 BUY")
    fx_rows = data["fx"].get("rows", [])
    usdcny = data["fx"].get("live") or (fx_rows[-1]["close"] if fx_rows else None)
    fx_at = data["fx"].get("live_at") or (fx_rows[-1]["date"] if fx_rows else None)
    if usdcny is None and decision["state"] == "BUY":
        decision["state"] = "DATA_STALE"
        decision["reasons"] = ["USD/CNY 汇率缺失：停止生成 BUY"]
    events, alert_state = alert_events((prev or {}).get("alert_state"), decision, price if fresh != "STALE" else None, cfg)
    nb = next_band(decision.get("stage"), cfg)
    status = {
        "version": VERSION,
        "generated_at": iso(at),
        "module": cfg.get("module_version"),
        "freshness": cfg.get("freshness"),
        "gold": {
            "state": decision["state"],
            "review_kind": decision.get("review_kind"),
            "zone": decision["zone"],
            "stage": decision.get("stage"),
            "stage_budget_pct": decision.get("stage_budget_pct"),
            "reasons": decision.get("reasons", []),
            "blockers": decision.get("blockers", []),
            "next_band": {"min": nb["min"], "max": nb["max"], "stage": nb["stage"]} if nb else None,
            "quote": {
                "price": rnd(price), "basis": live.get("basis"), "source": live.get("source"),
                "as_of": live.get("as_of"), "freshness": fresh, "age_minutes": rnd(age, 1),
                "market_open": gold_market_open(at), "errors": live.get("fallback_errors") or data["live"].get("errors"),
            },
            "fx": {"usdcny": rnd(usdcny, 4), "as_of": fx_at, "source": data["fx"].get("source")},
            "cny_per_gram": rnd(cny_per_gram(price, usdcny)),
            "band_cny_per_gram": [
                {"usd": v, "cny_per_gram": rnd(cny_per_gram(v, usdcny))}
                for v in sorted({s["max"] for s in cfg["stages"]} | {s["min"] for s in cfg["stages"]}, reverse=True)
            ] if usdcny else [],
            "year_stats": year_stats(daily, fx_rows, at.year, cfg, price, basis=data["daily"].get("basis") or "spot"),
            "etf_quotes": data.get("etf", {}),
            "rules": {"pause": decision["pause"], "deep_review": decision["deep_review"],
                      "confirmation": decision["confirmation"]},
            "inputs": {
                "daily": {"source": data["daily"].get("source"), "basis": data["daily"].get("basis"),
                          "futures_spot_basis": data["daily"].get("futures_spot_basis"),
                          "last_date": daily[-1]["date"] if daily else None, "fresh": daily_fresh},
                "real_yield": {"source": data["real_yield"].get("source"),
                               "last_date": ry[-1]["date"] if ry else None, "last": rnd(ry[-1]["value"]) if ry else None},
                "dxy": {"source": data["dxy"].get("source"), "last_date": dxy[-1]["date"] if dxy else None,
                        "last": rnd(dxy[-1]["close"]) if dxy else None},
                "macro_fresh": macro_fresh,
                "etf_flows": "unavailable_free_source",
            },
            "stages": cfg["stages"],
            "reserved_pct": cfg["reserved_pct"],
            "core_watch_zone": cfg["core_watch_zone_usd_oz"],
            "events_this_run": events,
        },
        "dca_calendar": {
            "timezone": "Asia/Shanghai",
            "rule": "每月 7–10 日；遇周末/美股休市顺延至下一美股交易日",
            "symbols": list((dca_cfg.get("weights") or {}).keys()),
            "months": dca_calendar(at.astimezone(SH).date(), dca_cfg),
            "quotes": data.get("dca_quotes", {}),
        },
        "alert_state": alert_state,
        "guardrails": {
            "automatic_orders": False,
            "private_allocations_published": False,
            "buy_requires_fresh_spot_and_rules": True,
            "risk_pause_precedes_buy": True,
            "thresholds_are_initial_hypotheses": True,
        },
    }
    return status, decision, events


def main(argv=None):
    argv = argv or sys.argv[1:]
    cfg, dca_cfg = load_json(CONFIG), load_json(DCA_CONFIG)
    at = now_utc()
    data = collect()
    if "--probe" in argv:
        for k in ("live", "daily", "real_yield", "dxy", "fx"):
            d = data[k]
            n = len(d.get("rows", []))
            print(f"::notice title=Investment watch source probe::{k} ok={d.get('ok')} "
                  f"source={d.get('source')} basis={d.get('basis')} rows={n} "
                  f"last={(d.get('rows') or [{}])[-1].get('date') if n else d.get('as_of')} "
                  f"adj_basis={d.get('futures_spot_basis')} "
                  f"errors={d.get('errors') or d.get('fallback_errors') or d.get('error') or d.get('basis_adjust_error')}")
        print("::notice title=Investment watch source probe::etf " + json.dumps(
            {k: (v.get('price'), v.get('currency'), v.get('error')) for k, v in data['etf'].items()}))
        st, _, ev = build_status(data, cfg, dca_cfg, {}, at)  # dry run: nothing written or sent
        g = st["gold"]
        print("::notice title=Investment watch dry run::" + json.dumps({
            "state": g["state"], "zone": g["zone"], "stage": g["stage"], "price": g["quote"]["price"],
            "freshness": g["quote"]["freshness"], "cny_per_gram": g["cny_per_gram"], "fx": g["fx"]["usdcny"],
            "reasons": g["reasons"], "blockers": g["blockers"], "pause_met": g["rules"]["pause"]["met"],
            "ry_bp_5d": g["rules"]["pause"]["ry_change_bp_5d"], "dxy_pct_5d": g["rules"]["pause"]["dxy_change_pct_5d"],
            "confirmation": g["rules"]["confirmation"].get("detail"), "year_high": g["year_stats"].get("high"),
            "year_low": g["year_stats"].get("low"), "events_if_first_run": ev,
            "dca_window": st["dca_calendar"]["months"][0]}, ensure_ascii=False))
        return 0
    prev = load_json(OUT)
    status, decision, events = build_status(data, cfg, dca_cfg, prev, at)

    deliveries = []
    live = data["live"] if data["live"].get("ok") else {}
    private = private_gold_context() if "BUY_CONDITIONAL" in events else None
    for ev in events:
        deliveries.append(send_telegram(gold_message(ev, decision, live, cfg, data.get("etf"), private)))
    # A failed send (channel configured but Telegram error) keeps the previous
    # arming so the next run retries; not_configured advances (site still shows it).
    if any(str(d).startswith("failed") for d in deliveries) and (prev or {}).get("alert_state") is not None:
        status["alert_state"] = prev["alert_state"]
    status["gold"]["delivery"] = deliveries

    rows = journal_rows()
    if should_journal(rows, decision):
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(journal_entry(decision, live, at, cfg), ensure_ascii=False, sort_keys=True) + "\n")
        rows = journal_rows()
    status["gold"]["signal_id"] = rows[-1]["signal_id"] if rows else None
    outcomes = evaluate_outcomes(rows, data["daily"].get("rows", []))
    OUTCOMES.write_text(json.dumps({"generated_at": iso(at), "horizons": HORIZONS, "rows": outcomes},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    status["learning"] = {
        "journal_entries": len(rows),
        "mature": {f"{h}d": sum(1 for o in outcomes if o.get(f"mature_{h}d")) for h in HORIZONS},
        "capture_mode": "live_forward_state_entries",
        "rule_changes_from_immature_outcomes": False,
    }
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")

    dca = run_dca(at.astimezone(SH).date(), dca_cfg)
    g = status["gold"]
    print(f"::notice title=Investment watch::gold state={g['state']} zone={g['zone']} stage={g['stage']} "
          f"price={g['quote']['price']} freshness={g['quote']['freshness']} basis={g['quote']['basis']} "
          f"events={events} delivery={deliveries} journal={len(rows)}")
    print("::notice title=Investment watch DCA (aggregate)::" + json.dumps(dca, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
