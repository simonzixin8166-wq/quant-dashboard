#!/usr/bin/env python3
"""TP-01 变盘信号清单 (owner decisions #133 6235323449, 6307417998 + 10/21 confirmation).

Four conditions from an external author's turning-point view, tracked daily as an OBSERVATION list — not a buy/sell
signal, never an input to thresholds, positions or the add-on ladder. Thresholds are the author's, recorded as-is
(external view, unvalidated) so later outcomes can test them.

  1 earnings   Mega-cap earnings reaction: AAPL MSFT GOOG AMZN META NVDA. Event = SEC 8-K with Item 2.02 in the
               last 60 days (SEC submissions, free). Reaction = 5-session close-to-close return relative to QQQ
               from the last close before the release. ≥4 beating QQQ → met; 3 → near; waiting while the rest
               could still reach 3; not met once that is impossible.
               (Upcoming dates come later with UX-02; nothing here is estimated before a filing exists.)
  2 yield_10y  FRED DGS10 (from docs/research/macro_context.json): <4.8 met; <5.0 near; else not met.
  3 sentiment  市场温度 ≤25 within the last 10 readings AND QQQ beat DIA over 5 sessions → met; one of two → near.
  4 easing     FRED DCOILWTICO / T10YIE 20-observation change < 0; PPIACO / IR latest month-over-month ≤ 0.
               ≥3 of 4 easing → met; 2 → near. Fewer than 3 readable inputs → unavailable.
Overall: ≥3 conditions met → "转折条件成立" (one Telegram on the change into that state).
Every run appends one row per market date to research/archive/turning_point_observations.jsonl (append-only);
a row whose state newly reaches ≥3 met carries trigger=true and the QQQ baseline close for 20/60-session scoring.
Missing data is `unavailable`, never imputed. The page shows only the result (owner page principle 6290421775).
"""
from __future__ import annotations
import io, json, os, sys, urllib.request, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
MACRO = ROOT / "docs" / "research" / "macro_context.json"
TEMP_HIST = ROOT / "docs" / "research" / "market_temperature_history.json"
OUT = ROOT / "docs" / "research" / "turning_point_checklist.json"
OBS = ROOT / "research" / "archive" / "turning_point_observations.jsonl"
VERSION = 1
ET = ZoneInfo("America/New_York")
MEGACAPS = {"AAPL": 320193, "MSFT": 789019, "GOOG": 1652044, "AMZN": 1018724, "META": 1326801, "NVDA": 1045810}
EASING_SERIES = {"DCOILWTICO": "daily", "T10YIE": "daily", "PPIACO": "monthly", "IR": "monthly"}
EASING_NAMES = {"DCOILWTICO": "WTI 原油", "T10YIE": "10 年通胀预期", "PPIACO": "PPI", "IR": "进口价格"}
NAMES = {"earnings": "科技巨头财报", "yield_10y": "10 年期美债", "sentiment": "情绪出清", "easing": "通胀与油价缓解"}
TAG = "外部观点 · 未验证 · 观察用，不是买卖信号"


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def closes(zbytes: bytes, symbol: str):
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    name = next((n for n in z.namelist() if n.lower().rsplit("/", 1)[-1] == f"{symbol.lower()}_us_d.csv"), None)
    if not name:
        return []
    out = []
    for r in z.read(name).decode().strip().splitlines()[1:]:
        p = r.split(",")
        try:
            out.append((p[0], float(p[4])))
        except (IndexError, ValueError):
            continue
    return sorted(out)


def item(key, status, value, as_of=None, **extra):
    return {"key": key, "name": NAMES[key], "status": status, "value": value, "as_of": as_of, **extra}


# ---------- 1 earnings ----------
def reaction(prices, qqq, filed_date, accepted_et_hour):
    """5-session return relative to QQQ from the last close before the release; None until 5 sessions exist."""
    dates = [d for d, _ in prices]
    # release before the open counts against the prior close; otherwise against the filing day's close
    base_idx = max((i for i, d in enumerate(dates) if (d < filed_date if accepted_et_hour < 9.5 else d <= filed_date)), default=None)
    if base_idx is None or base_idx + 5 >= len(prices):
        return None
    base_d, end_d = dates[base_idx], dates[base_idx + 5]
    q = dict(qqq)
    if base_d not in q or end_d not in q:
        return None
    return (prices[base_idx + 5][1] / prices[base_idx][1] - 1) - (q[end_d] / q[base_d] - 1)


def latest_earnings_filing(submissions, today):
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms, dates, items, acc = (recent.get(k) or [] for k in ("form", "filingDate", "items", "acceptanceDateTime"))
    floor = (today - timedelta(days=60)).isoformat()
    for i, form in enumerate(forms):
        if form == "8-K" and i < len(items) and "2.02" in str(items[i]) and i < len(dates) and dates[i] >= floor:
            hour = 16.0
            try:
                t = datetime.fromisoformat(str(acc[i]).replace("Z", "+00:00")).astimezone(ET)
                hour = t.hour + t.minute / 60
            except Exception:
                pass
            return dates[i], hour
    return None


def sec_submissions(cik):
    ua = os.getenv("SEC_USER_AGENT", "MyAlphaView/6.9 research-agent myalphaview.com")
    req = urllib.request.Request(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                                 headers={"User-Agent": ua, "Accept": "application/json", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def earnings_condition(zbytes, today, fetch=sec_submissions):
    qqq = closes(zbytes, "QQQ")
    reported, scored, beat, errors = 0, 0, 0, 0
    for sym, cik in MEGACAPS.items():
        try:
            hit = latest_earnings_filing(fetch(cik), today)
        except Exception:
            errors += 1
            continue
        if not hit:
            continue
        reported += 1
        rel = reaction(closes(zbytes, sym), qqq, hit[0], hit[1])
        if rel is not None:
            scored += 1
            beat += rel > 0
    if errors > len(MEGACAPS) // 2:
        return item("earnings", "unavailable", "SEC 数据暂不可用")
    if reported == 0:
        return item("earnings", "waiting", f"本季尚未公布 · 0/{len(MEGACAPS)} 家", reported=0, scored=0, beat=0)
    best_case = beat + (len(MEGACAPS) - scored)  # companies not yet scored could still beat QQQ
    status = "met" if beat >= 4 else "near" if beat == 3 else "not_met" if best_case < 3 else "waiting"
    return item("earnings", status, f"{beat}/{scored} 家第 5 天跑赢 QQQ · 已公布 {reported}/{len(MEGACAPS)}",
                today.isoformat(), reported=reported, scored=scored, beat=beat)


# ---------- 2 yield ----------
def yield_condition(macro):
    latest = (((macro or {}).get("series") or {}).get("DGS10") or {}).get("latest") or {}
    v = latest.get("value")
    if not isinstance(v, (int, float)):
        return item("yield_10y", "unavailable", "10 年期收益率不可用")
    status = "met" if v < 4.8 else "near" if v < 5.0 else "not_met"
    return item("yield_10y", status, f"{v:.2f}%（需 < 5.0%，4.8% 以下更明确）", latest.get("date"), reading=v)


# ---------- 3 sentiment ----------
def sentiment_condition(temp_hist, zbytes):
    rows = [r for r in ((temp_hist or {}).get("rows") or []) if isinstance(r.get("score"), (int, float))][-10:]
    qqq, dia = closes(zbytes, "QQQ"), closes(zbytes, "DIA")
    if not rows or len(qqq) < 6 or len(dia) < 6:
        return item("sentiment", "unavailable", "市场温度或 QQQ/DIA 数据不可用")
    flush = min(r["score"] for r in rows) <= 25
    rel = (qqq[-1][1] / qqq[-6][1] - 1) - (dia[-1][1] / dia[-6][1] - 1)
    lead = rel > 0
    hits = flush + lead
    status = "met" if hits == 2 else "near" if hits == 1 else "not_met"
    text = f"近 10 日市场温度最低 {min(r['score'] for r in rows)} · 科技{'强于' if lead else '弱于'}道指"
    return item("sentiment", status, text, rows[-1].get("as_of"), temp_min=min(r["score"] for r in rows), qqq_minus_dia_5d=round(rel, 4))


# ---------- 4 easing ----------
def fred_rows(series_id):
    from fred_client import clean_value, series_observations
    start = (datetime.now(timezone.utc).date() - timedelta(days=200)).isoformat()
    out = []
    for r in series_observations(series_id, observation_start=start):
        v = clean_value(r.get("value"))
        if v is not None:
            out.append((r.get("date"), v))
    return out


def easing_condition(previous, fetch=fred_rows):
    cached = ((previous or {}).get("inputs") or {}).get("easing") or {}
    inputs, easing, readable, newest = {}, 0, 0, None
    for sid, freq in EASING_SERIES.items():
        try:
            rows = fetch(sid)
            if freq == "daily":
                if len(rows) < 21:
                    raise ValueError("short")
                change = rows[-1][1] - rows[-21][1]
            else:
                if len(rows) < 2 or not rows[-2][1]:
                    raise ValueError("short")
                change = rows[-1][1] / rows[-2][1] - 1
            inputs[sid] = {"date": rows[-1][0], "change": round(change, 6), "easing": change < 0 if freq == "daily" else change <= 0}
        except Exception:
            if isinstance(cached.get(sid), dict):
                inputs[sid] = {**cached[sid], "cached": True}
            else:
                inputs[sid] = None
        if inputs[sid]:
            readable += 1
            easing += bool(inputs[sid]["easing"])
            newest = max(filter(None, [newest, inputs[sid]["date"]]))
    if readable < 3:
        return item("easing", "unavailable", "通胀与油价数据不足"), inputs
    status = "met" if easing >= 3 else "near" if easing == 2 else "not_met"
    names = "、".join(EASING_NAMES[s] for s, v in inputs.items() if v and v["easing"]) or "无"
    return item("easing", status, f"{easing}/{readable} 项在缓解（{names}）", newest, easing=easing, readable=readable), inputs


# ---------- overall ----------
def overall(items):
    met = sum(1 for x in items if x["status"] == "met")
    near = sum(1 for x in items if x["status"] == "near")
    unavailable = sum(1 for x in items if x["status"] == "unavailable")
    if met >= 3:
        headline, action = f"{met} / 4 满足 · 转折条件成立", "外部观点所说的转折条件已成立（未验证）：建议重新评估节奏，是否行动仍由你按自己的规则决定。"
    else:
        headline = f"{met} / 4 满足" + (f"、{near} 项接近" if near else "") + " · 尚未出现转折条件"
        action = "继续按原计划定投，不因本清单加减仓；满足 3 项时会提醒你重新评估。"
    return {"met": met, "near": near, "unavailable": unavailable, "triggered": met >= 3, "headline": headline, "action": action}


def market_date(zbytes):
    spy = closes(zbytes, "SPY") or closes(zbytes, "QQQ")
    return spy[-1][0] if spy else None


def notify(text):
    try:
        from daily_guardian import send_telegram
        return send_telegram(text)
    except Exception as exc:
        return f"failed:{type(exc).__name__}"


def append_observation(row):
    OBS.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if OBS.exists():
        for line in OBS.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line).get("market_date"))
            except Exception:
                continue
    if row["market_date"] in seen:
        return False
    with OBS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def build(now=None, sec_fetch=sec_submissions, fred_fetch=fred_rows, send=notify):
    now = now or datetime.now(timezone.utc)
    previous = load(OUT, {}) or {}
    zbytes = ARCHIVE.read_bytes() if ARCHIVE.exists() else b""
    try:
        zipfile.ZipFile(io.BytesIO(zbytes))
    except Exception:
        zbytes = io.BytesIO()
        zipfile.ZipFile(zbytes, "w").close()
        zbytes = zbytes.getvalue()
    today = now.astimezone(ET).date()
    easing, easing_inputs = easing_condition(previous, fred_fetch)
    items = [earnings_condition(zbytes, today, sec_fetch), yield_condition(load(MACRO, {})),
             sentiment_condition(load(TEMP_HIST, {}), zbytes), easing]
    summary = overall(items)
    mdate = market_date(zbytes)
    newly = summary["triggered"] and not ((previous.get("summary") or {}).get("triggered"))
    delivery = "not_needed"
    if newly:
        delivery = send("MyAlpha｜变盘信号清单：4 项中已有 %d 项满足（外部观点，未验证）。\n%s\n这是观察提醒，不是买卖信号；请按你的规则人工决定。"
                        % (summary["met"], "；".join(f"{x['name']}：{x['value']}" for x in items if x["status"] == "met")))
    out = {
        "version": VERSION, "generated_at": now.isoformat(), "market_date": mdate, "tag": TAG,
        "summary": summary, "items": items, "inputs": {"easing": easing_inputs},
        "delivery": delivery, "validated": False, "production_use": False,
        "policy": "observation list from an external author's view; never changes thresholds, positions or the add-on ladder",
    }
    if mdate:
        qqq = closes(zbytes, "QQQ")
        append_observation({"market_date": mdate, "v": VERSION, "met": summary["met"], "near": summary["near"],
                            "statuses": {x["key"]: x["status"] for x in items}, "trigger": bool(newly),
                            "qqq_close": qqq[-1][1] if qqq and qqq[-1][0] == mdate else None,
                            "recorded_at": now.isoformat()})
    return out


def main():
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"market_date": out["market_date"], "summary": out["summary"],
                      "statuses": {x["key"]: x["status"] for x in out["items"]}, "delivery": out["delivery"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
