#!/usr/bin/env python3
"""Paper simulation of a forum member's QQQ/TQQQ 200-day-average strategy with 5,000 USD (Owner 2026-11-25).

Back end only. No order is ever placed, no broker is contacted, nothing is published on the site, and nothing here
feeds a MyAlpha decision, threshold or alert. It answers one question in real time: what would this strategy have
done with 5,000 USD from 2026-11-25 on, compared with simply holding QQQ?

Rules (forum post bbs.wenxuecity.com/tzlc/2414333, 2026-11-24; ambiguous parts fixed as written below):
  QQQ close >= its 200-day simple average ("above"):
    hold 100% TQQQ; take profit (all to cash) when QQQ close >= 1.15 x average; after a take-profit, buy TQQQ back
    without waiting for the next cycle once QQQ closes 10% above its take-profit close ("10%过前高再买").
  QQQ close < average ("below"):
    no TQQQ; QQQ weight = 8% per full 1% below the average, measured at the deepest close since the cross,
    buy only, never sell, capped at 100%.
Signals are taken at each session close and filled at the NEXT session's open (Owner 2026-11-25: buy at the next
open); each trade costs 0.05% of the amount traded; cash earns nothing.
Start (Owner 2026-11-25: "start today, from yesterday's close"): the first signal is the 2026-11-24 close, where the
strategy holds 80% QQQ (deepest close since the 11/13 cross: -10.6% on 11/20); 5,000 USD is invested at the
2026-11-25 open. A 5,000 USD QQQ buy-and-hold account is bought at the same open.

Writes research/sim/tqqq_ma200_state.json and appends research/sim/tqqq_ma200_ledger.jsonl (one row per session).
Data: data/history/stooq_watchlist.zip (qqq_us_d.csv, tqqq_us_d.csv), refreshed earlier in the Daily run.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
OUT_DIR = ROOT / "research" / "sim"
STATE = OUT_DIR / "tqqq_ma200_state.json"
LEDGER = OUT_DIR / "tqqq_ma200_ledger.jsonl"
VERSION = "sim-tqqq-ma200-0.1"
START_CASH = 5000.0
SIGNAL_FROM = "2026-11-24"   # Owner 2026-11-25: start from today, using yesterday's close
COST = 0.0005
STEP_PER_PCT = 0.08
TAKE_PROFIT = 1.15
REENTRY_ABOVE_TP = 1.10


def load_bars(archive: Path = ARCHIVE) -> tuple[dict, dict, dict, dict]:
    """(qqq_close, tqqq_close, qqq_open, tqqq_open) keyed by date."""
    with zipfile.ZipFile(archive) as z:
        def one(name, col):
            return {r["Date"]: float(r[col]) for r in csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8"))
                    if r.get(col) not in (None, "", "null")}
        return (one("qqq_us_d.csv", "Close"), one("tqqq_us_d.csv", "Close"),
                one("qqq_us_d.csv", "Open"), one("tqqq_us_d.csv", "Open"))


def sma200(qqq: dict, day: str):
    ds = [d for d in sorted(qqq) if d <= day][-200:]
    return sum(qqq[d] for d in ds) / 200 if len(ds) == 200 else None


def deepest_since_cross(qqq: dict, day: str) -> float:
    """Most negative close/average - 1 since the last close at or above the average (0 if above today)."""
    ds = [d for d in sorted(qqq) if d <= day]
    worst = 0.0
    for d in reversed(ds):
        s = sma200(qqq, d)
        if s is None:
            break
        dev = qqq[d] / s - 1
        if dev >= 0:
            break
        worst = min(worst, dev)
    return worst


def ratchet_weight(worst_dev: float) -> float:
    return min(1.0, STEP_PER_PCT * math.floor(-worst_dev * 100)) if worst_dev < 0 else 0.0


def value(st: dict, q: float, t: float) -> float:
    return st["cash"] + st["qqq_sh"] * q + st["tqqq_sh"] * t


def rebalance(st: dict, q: float, t: float, w_q: float, w_t: float) -> dict | None:
    """Move to target weights at the given prices (the session open); returns the trade or None when nothing moves."""
    v = value(st, q, t)
    tq_now, tt_now = st["qqq_sh"] * q, st["tqqq_sh"] * t
    tq_new, tt_new = v * w_q, v * w_t
    turnover = abs(tq_new - tq_now) + abs(tt_new - tt_now)
    if turnover < 1.0:
        return None
    cost = turnover * COST
    v -= cost
    tq_new, tt_new = v * w_q, v * w_t
    st.update(qqq_sh=tq_new / q, tqqq_sh=tt_new / t, cash=v - tq_new - tt_new)
    return {"qqq_usd": round(tq_new - tq_now, 2), "tqqq_usd": round(tt_new - tt_now, 2), "cost": round(cost, 2)}


def signal(st: dict, q: float, s: float, qqq_weight_now: float, holds_tqqq: bool) -> tuple[str, float, float]:
    """Rules at one session close -> (reason, target QQQ weight, target TQQQ weight) for the next session's open."""
    dev = q / s - 1
    st["prior_high"] = max(st.get("prior_high") or 0.0, q)
    if dev >= 0:
        st["worst_dev"] = 0.0
        if st.get("tp_done"):
            if q > REENTRY_ABOVE_TP * st["tp_high"]:
                st["tp_done"] = False
                return "re-enter TQQQ: QQQ 10% above its take-profit close", 0.0, 1.0
            return "after take-profit: wait in cash until QQQ is 10% above the take-profit close", 0.0, 0.0
        if q >= TAKE_PROFIT * s and holds_tqqq:
            st.update(tp_done=True, tp_high=q)
            return "take profit: QQQ >= 1.15 x 200-day average", 0.0, 0.0
        return "above the 200-day average: hold TQQQ", 0.0, 1.0
    st["tp_done"] = False
    st["worst_dev"] = min(st.get("worst_dev") or 0.0, dev)
    w = ratchet_weight(st["worst_dev"])
    if not holds_tqqq:
        w = max(w, qqq_weight_now)         # buy only: never sell QQQ below the average
    return f"below the 200-day average: QQQ {w:.0%} (deepest {st['worst_dev']:.1%}, buy only)", w, 0.0


def run(qqq: dict, tqqq: dict, qopen: dict, topen: dict, state: dict | None, now: datetime) -> tuple[dict, list[dict]]:
    """Signal at each close, filled at the next session's open (Owner 2026-11-25). The first signal is the
    SIGNAL_FROM close; the account opens with 5,000 USD at the open of the session after it."""
    days = [d for d in sorted(qqq) if d >= SIGNAL_FROM and d in tqqq]
    rows = []
    if not days:
        return state or {}, rows
    st = state
    if not st:
        d0 = days[0]
        st = {"version": VERSION, "signal_from": d0, "started": None, "cash": START_CASH, "qqq_sh": 0.0, "tqqq_sh": 0.0,
              "worst_dev": deepest_since_cross(qqq, d0) if qqq[d0] < (sma200(qqq, d0) or 0) else 0.0,
              "tp_done": False, "tp_high": None, "prior_high": max(v for d, v in qqq.items() if d <= d0),
              "bench_qqq_sh": None, "pending": None, "last_day": None, "trades": 0}
    for d in days:
        if st["last_day"] and d <= st["last_day"]:
            continue
        s = sma200(qqq, d)
        if s is None:
            continue
        trade = None
        if st["pending"] and d in qopen and d in topen:           # fill yesterday's signal at today's open
            if st["started"] is None:
                st["started"] = d
                st["bench_qqq_sh"] = START_CASH * (1 - COST) / qopen[d]
            pw_q, pw_t = st["pending"]["w_q"], st["pending"]["w_t"]
            if pw_t == 0 and st["tqqq_sh"] == 0 and pw_q > 0:        # below the average: buy only, never trim QQQ
                vo = value(st, qopen[d], topen[d])
                pw_q = max(pw_q, st["qqq_sh"] * qopen[d] / vo if vo else 0.0)
            trade = rebalance(st, qopen[d], topen[d], pw_q, pw_t)
            st["trades"] += 1 if trade else 0
            filled = st["pending"]
        else:
            filled = None
        q, t = qqq[d], tqqq[d]
        v = value(st, q, t)
        reason, w_q, w_t = signal(st, q, s, (st["qqq_sh"] * q / v) if v else 0.0, st["tqqq_sh"] > 0)
        st["pending"] = {"signal_date": d, "w_q": w_q, "w_t": w_t, "reason": reason}
        st["last_day"] = d
        if st["started"] is None:
            rows.append({"date": d, "kind": "first_signal", "qqq": q, "sma200": round(s, 2), "dev": round(q / s - 1, 4),
                         "next_open_target": {"qqq": w_q, "tqqq": w_t}, "reason": reason,
                         "recorded_at": now.isoformat(timespec="seconds")})
            continue
        b = st["bench_qqq_sh"] * q
        rows.append({"date": d, "qqq": q, "tqqq": t, "qqq_open": qopen.get(d), "tqqq_open": topen.get(d),
                     "sma200": round(s, 2), "dev": round(q / s - 1, 4),
                     "filled_at_open": ({"signal_date": filled["signal_date"], "reason": filled["reason"], "trade": trade}
                                        if filled else None),
                     "holding_at_close": {"qqq_usd": round(st["qqq_sh"] * q, 2), "tqqq_usd": round(st["tqqq_sh"] * t, 2),
                                          "cash_usd": round(st["cash"], 2)},
                     "value": round(v, 2), "return": round(v / START_CASH - 1, 4),
                     "benchmark_qqq_value": round(b, 2), "benchmark_return": round(b / START_CASH - 1, 4),
                     "next_open_target": {"qqq": w_q, "tqqq": w_t}, "reason": reason,
                     "recorded_at": now.isoformat(timespec="seconds")})
    return st, rows


def summary(st: dict, rows_all: list[dict]) -> dict:
    if not rows_all:
        return {"status": "waiting for the first signal close on or after " + SIGNAL_FROM}
    rows_all = [r for r in rows_all if r.get("kind") != "first_signal"]
    if not rows_all:
        return {"status": "first signal recorded; the account opens at the next session's open"}
    vals = [r["value"] for r in rows_all]
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    last = rows_all[-1]
    return {"status": "running", "started": st["started"], "as_of": last["date"], "sessions": len(rows_all),
            "value": last["value"], "return": last["return"], "max_drawdown": round(mdd, 4),
            "benchmark_qqq_value": last["benchmark_qqq_value"], "benchmark_return": last["benchmark_return"],
            "holding_at_close": last["holding_at_close"], "trades": st["trades"], "next_open_target": last["next_open_target"],
            "last_reason": last["reason"]}


def main() -> int:
    qqq, tqqq, qopen, topen = load_bars()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
    now = datetime.now(timezone.utc)
    st, rows = run(qqq, tqqq, qopen, topen, state and state.get("account"), now)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if rows:
        with LEDGER.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    all_rows = [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines()] if LEDGER.exists() else []
    doc = {"version": VERSION, "generated_at": now.isoformat(timespec="seconds"), "account": st,
           "summary": summary(st, all_rows), "paper_only": True, "orders_placed": False, "published": False,
           "policy_zh": "网友均线 + TQQQ 策略的纸面模拟（5,000 美元），不下单、不连券商、不上网站、不影响系统任何提醒和阈值。"}
    STATE.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
