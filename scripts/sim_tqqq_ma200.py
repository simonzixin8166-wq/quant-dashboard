#!/usr/bin/env python3
"""Paper simulation of a forum member's QQQ/TQQQ 200-day-average strategy with 5,000 USD (Owner 2026-11-25).

No order is ever placed and no broker is contacted; the homepage shows only the paper result; nothing here
feeds a MyAlpha decision, threshold or alert. It answers one question in real time: what would this strategy have
done with 5,000 USD from 2026-11-25 on, compared with simply holding QQQ?

Rules (forum post bbs.wenxuecity.com/tzlc/2414333, 2026-11-24; ambiguous parts fixed as written below):
  QQQ close >= its 200-day simple average ("above"):
    hold 100% TQQQ; take profit (all to cash) when QQQ close >= 1.15 x average; after a take-profit, buy TQQQ back
    without waiting for the next cycle once QQQ closes 10% above its take-profit close ("10%过前高再买").
    Revision 2026-11-26 (Owner): after such a buy-back the take-profit is disarmed until QQQ closes below
    1.15 x average again, so a buy-back is not sold at the very next close (5 of 11 buy-backs since 2010 were).
  QQQ close < average ("below"):
    no TQQQ; QQQ weight = 8% per full 1% below the average, measured at the deepest close since the cross,
    buy only, never sell, capped at 100%.
Signals are taken at each session close and filled at the NEXT session's open (Owner 2026-11-25: buy at the next
open). Owner 2026-11-25: trades are kept like an IBKR account: whole shares at the open price, IBKR Pro Fixed
commission (0.005 USD/share, min 1 USD, max 1%), a fill record per order (date, side, symbol, shares, price,
amount, commission, realized P/L on sells), positions with average cost; cash earns nothing.
Start (Owner 2026-11-25: "start today, from yesterday's close"): the first signal is the 2026-11-24 close, where the
strategy holds 80% QQQ (deepest close since the 11/13 cross: -10.6% on 11/20); 5,000 USD is invested at the
2026-11-25 open. A 5,000 USD QQQ buy-and-hold account is bought at the same open.

Writes research/sim/tqqq_ma200_state.json, appends research/sim/tqqq_ma200_ledger.jsonl (one row per session and
account) and, for the homepage card (Owner 2026-11-25), docs/research/sim_tqqq_ma200.json with paper values only.
Books (Owner 2026-11-26): "band2" (the rule above with a +/-2% band), "ema530" (forum blogger YIFAN's rule: all-in
TQQQ the open after EMA5 of the TQQQ close crosses above EMA30, all cash the open after it crosses below), "hybrid"
(band2, except that below the average, while the 530 signal is on, it holds 50% TQQQ and 50% cash, and returns to the
QQQ ladder after the 530 death cross; pre-registered 2026-11-26 before any forward data) and the QQQ buy-and-hold
benchmark. The "original" book (no band) was retired on 2026-11-26.
Data: data/history/stooq_watchlist.zip (qqq_us_d.csv, tqqq_us_d.csv), refreshed earlier in the Daily run.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import math
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
OUT_DIR = ROOT / "research" / "sim"
STATE = OUT_DIR / "tqqq_ma200_state.json"
LEDGER = OUT_DIR / "tqqq_ma200_ledger.jsonl"
VERSION = "sim-tqqq-ma200-0.3"   # 0.2: take-profit re-arms below 1.15 x average; 0.3: four books (2026-11-26)
START_CASH = 5000.0
SIGNAL_FROM = "2026-11-24"   # Owner 2026-11-25: start from today, using yesterday's close
COST = 0.0005
STEP_PER_PCT = 0.08
TAKE_PROFIT = 1.15
REENTRY_ABOVE_TP = 1.10
HYBRID_TQQQ = 0.5      # hybrid book: TQQQ weight below the average while the 530 signal is on (pre-registered 2026-11-26)


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


def commission(shares: int, price: float) -> float:
    """IBKR Pro Fixed (US stocks/ETFs): 0.005 USD per share, minimum 1.00 USD, at most 1% of the trade value."""
    if shares <= 0:
        return 0.0
    return round(min(max(1.0, 0.005 * shares), 0.01 * shares * price), 2)


def _book(st: dict, sym: str) -> dict:
    return st.setdefault("positions", {}).setdefault(sym, {"shares": 0, "cost": 0.0})


def rebalance(st: dict, q: float, t: float, w_q: float, w_t: float, day: str = "", buy_only_qqq: bool = False,
              keep_tqqq: bool = False) -> list[dict]:
    """Owner 2026-11-25: trade like an IBKR account. Whole shares at the session open, sells first, then buys with
    the cash on hand, IBKR Pro Fixed commission per order; average cost and realized P/L kept per symbol.
    Returns the fills (empty when nothing changes)."""
    prices = {"QQQ": q, "TQQQ": t}
    key = {"QQQ": "qqq_sh", "TQQQ": "tqqq_sh"}
    v = value(st, q, t)
    want = {"QQQ": int(v * w_q // q) if w_q > 0 else 0, "TQQQ": int(v * w_t // t) if w_t > 0 else 0}
    if keep_tqqq:
        want["TQQQ"] = int(st["tqqq_sh"])     # same partial TQQQ target as yesterday: no daily drift trades
    if buy_only_qqq:
        want["QQQ"] = max(want["QQQ"], int(st["qqq_sh"]))
    fills = []
    for sym in ("QQQ", "TQQQ"):                                    # sells first
        have = int(st[key[sym]])
        n = have - want[sym]
        if n > 0:
            px, b = prices[sym], _book(st, sym)
            fee = commission(n, px)
            avg = b["cost"] / b["shares"] if b["shares"] else 0.0
            pnl = round((px - avg) * n - fee, 2)
            st["cash"] += n * px - fee
            b["cost"] -= avg * n; b["shares"] -= n
            st[key[sym]] = have - n
            st["realized_pnl"] = round((st.get("realized_pnl") or 0.0) + pnl, 2)
            fills.append({"date": day, "side": "SELL", "symbol": sym, "shares": n, "price": round(px, 2),
                          "amount": round(n * px, 2), "commission": fee, "realized_pnl": pnl})
    for sym in ("QQQ", "TQQQ"):                                    # then buys, within the cash on hand
        have = int(st[key[sym]])
        n = want[sym] - have
        if n > 0:
            px = prices[sym]
            while n > 0 and n * px + commission(n, px) > st["cash"] + 1e-9:
                n -= 1
            if n <= 0:
                continue
            fee = commission(n, px)
            st["cash"] -= n * px + fee
            b = _book(st, sym)
            b["shares"] += n; b["cost"] += n * px + fee
            st[key[sym]] = have + n
            fills.append({"date": day, "side": "BUY", "symbol": sym, "shares": n, "price": round(px, 2),
                          "amount": round(n * px, 2), "commission": fee})
    st["cash"] = round(st["cash"], 2)
    st.setdefault("fills", []).extend(fills)
    return fills


def positions(st: dict, q: float, t: float) -> list[dict]:
    """IBKR-style position lines at a close: shares, average cost, last price, market value, unrealized P/L."""
    out = []
    for sym, px in (("QQQ", q), ("TQQQ", t)):
        b = (st.get("positions") or {}).get(sym) or {"shares": 0, "cost": 0.0}
        if b["shares"] <= 0:
            continue
        avg = b["cost"] / b["shares"]
        out.append({"symbol": sym, "shares": b["shares"], "avg_cost": round(avg, 2), "price": round(px, 2),
                    "market_value": round(b["shares"] * px, 2), "unrealized_pnl": round(b["shares"] * (px - avg), 2),
                    "unrealized_pct": round(px / avg - 1, 4)})
    return out


def signal(st: dict, q: float, s: float, qqq_weight_now: float, holds_tqqq: bool, band: float = 0.0
           ) -> tuple[str, float, float]:
    """Rules at one session close -> (reason, target QQQ weight, target TQQQ weight) for the next session's open.
    band = 0 is the forum rule (cross the average); band = 0.02 is the comparison account: above only once QQQ is
    2% over the average, below only once it is 2% under it (Owner 2026-11-25, fewer whipsaws)."""
    dev = q / s - 1
    if q < TAKE_PROFIT * s:
        st["tp_armed"] = True              # Owner 2026-11-26: re-arm only after QQQ is back under 1.15 x average
    st["prior_high"] = max(st.get("prior_high") or 0.0, q)
    mode = st.get("mode")
    if mode != "above" and dev >= band:
        mode = "above"
    elif mode != "below" and dev < -band:
        mode, st["worst_dev"] = "below", dev
    elif mode is None:
        mode = "above" if dev >= 0 else "below"
    st["mode"] = mode
    if mode == "above":
        st["worst_dev"] = 0.0
        if st.get("tp_done"):
            if q > REENTRY_ABOVE_TP * st["tp_high"]:
                st["tp_done"] = False
                st["tp_armed"] = False
                return "re-enter TQQQ: QQQ 10% above its take-profit close", 0.0, 1.0
            return "after take-profit: wait in cash until QQQ is 10% above the take-profit close", 0.0, 0.0
        if q >= TAKE_PROFIT * s and holds_tqqq and st.get("tp_armed", True):
            st.update(tp_done=True, tp_high=q)
            return "take profit: QQQ >= 1.15 x 200-day average", 0.0, 0.0
        return "above the 200-day average" + (f" (+{band:.0%} band)" if band else "") + ": hold TQQQ", 0.0, 1.0
    st["tp_done"] = False
    st["worst_dev"] = min(st.get("worst_dev") or 0.0, dev)
    w = ratchet_weight(st["worst_dev"])
    if not holds_tqqq:
        w = max(w, qqq_weight_now)         # buy only: never sell QQQ below the average
    return f"below the 200-day average: QQQ {w:.0%} (deepest {st['worst_dev']:.1%}, buy only)", w, 0.0


def ema_series(closes: dict, span: int) -> dict:
    """EMA of the close, pandas ewm(span, adjust=False) (the blogger's script), over the whole history."""
    a, e, out = 2 / (span + 1), None, {}
    for d in sorted(closes):
        e = closes[d] if e is None else a * closes[d] + (1 - a) * e
        out[d] = e
    return out


def ema530_step(st: dict, e5: dict, e30: dict, d: str, prev: str | None) -> bool:
    """YIFAN 530 (Owner 2026-11-26): ON after EMA5 crosses above EMA30 of the TQQQ close, OFF after it crosses below.
    Only crosses switch it (as in the blogger's script), so a book starts OFF until the first golden cross."""
    if prev is not None and d in e5 and prev in e5:
        if e5[prev] <= e30[prev] and e5[d] > e30[d]:
            st["e530_on"] = True
        elif e5[prev] >= e30[prev] and e5[d] < e30[d]:
            st["e530_on"] = False
    return bool(st.get("e530_on"))


def run(qqq: dict, tqqq: dict, qopen: dict, topen: dict, state: dict | None, now: datetime, band: float = 0.0,
        kind: str = "ma200") -> tuple[dict, list[dict]]:
    """Signal at each close, filled at the next session's open (Owner 2026-11-25). The first signal is the
    SIGNAL_FROM close; the account opens with 5,000 USD at the open of the session after it."""
    days = [d for d in sorted(qqq) if d >= SIGNAL_FROM and d in tqqq]
    rows = []
    tdays = sorted(tqqq)
    prev_of = dict(zip(tdays[1:], tdays[:-1]))
    e5, e30 = (ema_series(tqqq, 5), ema_series(tqqq, 30)) if kind != "ma200" else ({}, {})
    if not days:
        return state or {}, rows
    st = state
    if not st:
        d0 = days[0]
        st = {"version": VERSION, "signal_from": d0, "started": None, "cash": START_CASH, "qqq_sh": 0, "tqqq_sh": 0,
              "positions": {}, "fills": [], "realized_pnl": 0.0, "bench_cash": None,
              "worst_dev": deepest_since_cross(qqq, d0) if qqq[d0] < (sma200(qqq, d0) or 0) else 0.0,
              "mode": ("below" if qqq[d0] < (sma200(qqq, d0) or 0) else "above"), "band": band,
              "tp_done": False, "tp_high": None, "prior_high": max(v for d, v in qqq.items() if d <= d0),
              "bench_qqq_sh": None, "pending": None, "last_day": None, "trades": 0}
    for d in days:
        if st["last_day"] and d <= st["last_day"]:
            continue
        s = sma200(qqq, d)
        if s is None:
            continue
        fills = []
        if st["pending"] and d in qopen and d in topen:           # fill yesterday's signal at today's open
            if st["started"] is None:
                st["started"] = d
                fee = commission(int((START_CASH - 1.0) // qopen[d]), qopen[d])
                st["bench_qqq_sh"] = int((START_CASH - fee) // qopen[d])
                st["bench_cash"] = round(START_CASH - st["bench_qqq_sh"] * qopen[d] - fee, 2)
                st["bench_px"] = round(qopen[d], 2)
            pw_q, pw_t = st["pending"]["w_q"], st["pending"]["w_t"]
            buy_only = pw_t == 0 and st["tqqq_sh"] == 0 and pw_q > 0   # below the average: never trim QQQ
            keep = (kind == "hybrid" and 0 < pw_t < 1 and st["tqqq_sh"] > 0 and st.get("last_w_t") == pw_t)
            fills = rebalance(st, qopen[d], topen[d], pw_q, pw_t, d, buy_only, keep)
            st["last_w_t"] = pw_t
            st["trades"] += len(fills)
            filled = st["pending"]
        else:
            filled = None
        q, t = qqq[d], tqqq[d]
        v = value(st, q, t)
        if kind == "ema530":
            on = ema530_step(st, e5, e30, d, prev_of.get(d))
            reason, w_q, w_t = (("530: EMA5 above EMA30 after a golden cross: hold TQQQ", 0.0, 1.0) if on else
                                ("530: after a death cross (or before the first golden cross): cash", 0.0, 0.0))
        else:
            reason, w_q, w_t = signal(st, q, s, (st["qqq_sh"] * q / v) if v else 0.0, st["tqqq_sh"] > 0, band)
            if kind == "hybrid":
                on = ema530_step(st, e5, e30, d, prev_of.get(d))
                if st.get("mode") == "below" and on:
                    reason, w_q, w_t = ("hybrid: below the 200-day average but the 530 signal is on: 50% TQQQ, 50% cash",
                                        0.0, HYBRID_TQQQ)
        st["pending"] = {"signal_date": d, "w_q": w_q, "w_t": w_t, "reason": reason}
        st["last_day"] = d
        if st["started"] is None:
            rows.append({"date": d, "kind": "first_signal", "qqq": q, "sma200": round(s, 2), "dev": round(q / s - 1, 4),
                         "next_open_target": {"qqq": w_q, "tqqq": w_t}, "reason": reason,
                         "recorded_at": now.isoformat(timespec="seconds")})
            continue
        b = st["bench_qqq_sh"] * q + (st.get("bench_cash") or 0.0)
        rows.append({"date": d, "qqq": q, "tqqq": t, "qqq_open": qopen.get(d), "tqqq_open": topen.get(d),
                     "sma200": round(s, 2), "dev": round(q / s - 1, 4),
                     "filled_at_open": ({"signal_date": filled["signal_date"], "reason": filled["reason"], "fills": fills}
                                        if filled else None),
                     "positions": positions(st, q, t), "cash_usd": round(st["cash"], 2),
                     "holding_at_close": {"qqq_usd": round(st["qqq_sh"] * q, 2), "tqqq_usd": round(st["tqqq_sh"] * t, 2),
                                          "cash_usd": round(st["cash"], 2)},
                     "realized_pnl": st.get("realized_pnl", 0.0),
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
    def _mdd(vals):
        peak, m = vals[0], 0.0
        for v in vals:
            peak = max(peak, v); m = min(m, v / peak - 1)
        return m
    mdd = _mdd([r["value"] for r in rows_all])
    last = rows_all[-1]
    return {"status": "running", "started": st["started"], "as_of": last["date"], "sessions": len(rows_all),
            "value": last["value"], "return": last["return"], "max_drawdown": round(mdd, 4),
            "benchmark_qqq_value": last["benchmark_qqq_value"], "benchmark_return": last["benchmark_return"],
            "benchmark_max_drawdown": round(_mdd([r["benchmark_qqq_value"] for r in rows_all]), 4),
            "benchmark_qqq_shares": st.get("bench_qqq_sh"), "benchmark_buy_price": st.get("bench_px"),
            "benchmark_cash": st.get("bench_cash"),
            "holding_at_close": last["holding_at_close"], "positions": last.get("positions", []),
            "cash_usd": last.get("cash_usd"), "realized_pnl": last.get("realized_pnl", 0.0),
            "fills": (st.get("fills") or [])[-30:],
            "trades": st["trades"], "next_open_target": last["next_open_target"],
            "last_reason": last["reason"]}


# Owner 2026-11-26: four 5,000 USD books from the same start (signal 2026-11-24 close, filled at the 11/25 open):
# band2 (our MA200 rule v0.2 with the +/-2% band), ema530 (YIFAN's 530 rule), hybrid (band2 + the 530 signal below the
# average, pre-registered here before any forward data) and the QQQ buy-and-hold benchmark. The "original" book
# (no band) was retired the same day; its ledger rows stay as written.
ACCOUNTS = {"band2": (0.02, "ma200"), "ema530": (0.0, "ema530"), "hybrid": (0.02, "hybrid")}
RETIRED = {"original": "2026-11-26"}
LABEL_ZH = {"band2": "均线策略（加 2% 缓冲）", "ema530": "530 策略（5/30 日均线交叉）",
            "hybrid": "均线 + 530 组合"}
PUBLIC = ROOT / "docs" / "research" / "sim_tqqq_ma200.json"


def public_card(doc: dict) -> dict:
    """What the homepage card shows: values, returns, holdings and the next open's target. Paper numbers only."""
    acc = {}
    for name, a in (doc.get("accounts") or {}).items():
        sm = a.get("summary") or {}
        acc[name] = {"label_zh": LABEL_ZH.get(name, name), "status": sm.get("status"), "as_of": sm.get("as_of"),
                     "started": sm.get("started"), "value": sm.get("value"), "return": sm.get("return"),
                     "max_drawdown": sm.get("max_drawdown"), "trades": sm.get("trades"),
                     "holding_at_close": sm.get("holding_at_close"), "next_open_target": sm.get("next_open_target"),
                     "positions": sm.get("positions"), "cash_usd": sm.get("cash_usd"),
                     "realized_pnl": sm.get("realized_pnl"), "fills": sm.get("fills"),
                     "last_reason": sm.get("last_reason")}
    bench = next((a.get("summary") for a in (doc.get("accounts") or {}).values()
                  if (a.get("summary") or {}).get("benchmark_qqq_value") is not None), {}) or {}
    return {"version": VERSION, "generated_at": doc.get("generated_at"), "start_cash": START_CASH,
            "accounts": acc, "order": list(ACCOUNTS),
            "benchmark": {"label_zh": "一直持有 QQQ", "value": bench.get("benchmark_qqq_value"),
                          "return": bench.get("benchmark_return"), "max_drawdown": bench.get("benchmark_max_drawdown"),
                          "qqq_shares": bench.get("benchmark_qqq_shares"), "buy_price": bench.get("benchmark_buy_price"),
                          "cash_usd": bench.get("benchmark_cash"), "started": bench.get("started"),
                          "as_of": bench.get("as_of")},
            "rules_zh": ("【均线策略】QQQ 在 200 日均线之上持有 TQQQ（到均线 1.15 倍止盈，比止盈价再高 10% 买回）；"
                         "跌破均线后每跌满 1% 买 8% QQQ，只买不卖。收盘出信号，第二天开盘价成交，按整股买卖，"
                         "佣金按 IBKR Pro 固定费率（每股 0.005 美元，每笔最低 1 美元）。"
                         "2026-11-26 修订：止盈后买回的 TQQQ，要等 QQQ 回落到均线 1.15 倍以下、再涨上来，才允许再次止盈"
                         "（避免买回第二天就卖）；这条是看过回测后定的，评估时单独标出。缓冲：高于均线 2% 才换 TQQQ，低于 2% 才转防守。"
                         "【530 策略】TQQQ 收盘价的 5 日线上穿 30 日线（金叉）第二天开盘满仓 TQQQ，下穿（死叉）第二天开盘全部卖出持有现金。"
                         "【组合】与均线策略相同；只在跌破均线期间，530 金叉时用一半资金买 TQQQ（其余现金），死叉后回到按跌幅分批买 QQQ。"
                         "【对比】开始那天开盘一次性买入 QQQ，一直持有。"),
            "paper_only": True, "orders_placed": False,
            "note_zh": "纸面模拟，不是买卖建议；不下单、不连券商，不影响系统任何提醒和阈值。"}


def planned_orders(st: dict, kind: str, q_close: float, t_close: float) -> list[dict]:
    """What the next open would trade for this book, estimated at the latest close (same rebalance code, on a copy)."""
    pend = st.get("pending") or {}
    if not pend or not st.get("started"):
        return []
    tmp = copy.deepcopy(st)
    pw_q, pw_t = pend["w_q"], pend["w_t"]
    buy_only = pw_t == 0 and tmp["tqqq_sh"] == 0 and pw_q > 0
    keep = (kind == "hybrid" and 0 < pw_t < 1 and tmp["tqqq_sh"] > 0 and tmp.get("last_w_t") == pw_t)
    return rebalance(tmp, q_close, t_close, pw_q, pw_t, "", buy_only, keep)


TARGET_ZH = lambda w_q, w_t: ("TQQQ %d%%" % round(w_t * 100) + ("，其余现金" if w_t < 1 else "") if w_t > 0 else  # noqa: E731
                              "QQQ %d%%，其余现金" % round(w_q * 100) if w_q > 0 else "全部现金")


def rehearsal_text(signal_day: str, plans: dict) -> str | None:
    """Owner 2026-11-26: on a signal day, a Telegram rehearsal note: what each paper book does at the next open.
    No reply is needed; the paper books execute by rule either way."""
    lines = []
    for name, (orders, pend) in plans.items():
        if not orders:
            continue
        acts = "；".join(("买入" if o["side"] == "BUY" else "卖出") + f" {o['symbol']} 约 {o['shares']} 股" for o in orders)
        lines.append(f"· {LABEL_ZH.get(name, name)}：{acts}（目标：{TARGET_ZH(pend['w_q'], pend['w_t'])}）")
    if not lines:
        return None
    return ("MyAlpha｜策略模拟演练提醒（纸面，不是真实下单）\n"
            f"{signal_day} 收盘出信号，下一个交易日开盘按开盘价成交：\n" + "\n".join(lines) + "\n"
            "股数按信号日收盘价估算，实际以开盘价为准。不需要回复，模拟账户会按规则自动记账。"
            "如果是真钱，你会在开盘前挂开盘单照做吗？")


def notify(text: str) -> str:
    if os.getenv("SIM_REHEARSAL_ALERTS_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return "disabled"
    try:
        from daily_guardian import send_telegram
        return send_telegram(text)
    except Exception as exc:  # noqa: BLE001
        return f"failed:{type(exc).__name__}"


def main() -> int:
    qqq, tqqq, qopen, topen = load_bars()
    prev = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    now = datetime.now(timezone.utc)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines()] if LEDGER.exists() else []
    accounts = {}
    for name, (band, kind) in ACCOUNTS.items():
        st, rows = run(qqq, tqqq, qopen, topen, ((prev.get("accounts") or {}).get(name) or {}).get("book"), now, band,
                       kind)
        if st.get("started") and not st.get("bench_px") and st["started"] in qopen:
            st["bench_px"] = round(qopen[st["started"]], 2)
        for r in rows:
            r["sim_book"] = name          # paper book name ("account" is reserved for real accounts by the canary)
            r["paper_only"] = True        # privacy scan: the owner-approved paper-sim exception keys on this flag
        if rows:
            with LEDGER.open("a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        all_rows += rows
        accounts[name] = {"band": band, "kind": kind, "book": st,
                          "summary": summary(st, [r for r in all_rows if r.get("sim_book", "original") == name])}
    # Owner 2026-11-26: rehearsal reminder, once per signal day, only when some book trades at the next open
    rehearsal = dict(prev.get("rehearsal") or {})
    last_day = max((a["book"].get("last_day") or "" for a in accounts.values()), default="")
    if last_day and last_day > (rehearsal.get("signal_day") or "") and last_day in qqq and last_day in tqqq:
        plans = {n: (planned_orders(a["book"], a["kind"], qqq[last_day], tqqq[last_day]), a["book"].get("pending") or {})
                 for n, a in accounts.items()}
        text = rehearsal_text(last_day, plans)
        rehearsal = {"signal_day": last_day, "status": notify(text) if text else "no_orders",
                     "orders": {n: len(p[0]) for n, p in plans.items()}}
    retired = dict(prev.get("retired_accounts") or {})
    for name, day in RETIRED.items():
        old = (prev.get("accounts") or {}).get(name)
        if old and name not in retired:
            retired[name] = {"retired_on": day, "last_summary": old.get("summary")}
    doc = {"version": VERSION, "generated_at": now.isoformat(timespec="seconds"), "accounts": accounts,
           "retired_accounts": retired, "rehearsal": rehearsal,
           "paper_only": True, "orders_placed": False,
           "policy_zh": "四个 5,000 美元纸面账户（均线策略加 2% 缓冲、530 策略、两者组合、一直持有 QQQ），同一天开始，不下单、不连券商，不影响系统任何提醒和阈值。"}
    STATE.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(public_card(doc), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in accounts.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
