#!/usr/bin/env python3
"""Core-ETF drawdown tier state (Owner-approved #133 6516033003 / 6537316711). Pure functions, no I/O.

Zones from calm to deep: normal < near < t1 < t2 < t3.
  near  = within NEAR_PP (2 percentage points) of tier 1 (Owner 10/31)
  t1-t3 = the existing CORE_TIERS thresholds on the validated ATH drawdown (unchanged; read from config)

Alerts are once per tier per drawdown cycle (a cycle starts at a new all-time high):
  enter X  - the first close at or beyond line X in this cycle
  leave X  - after X was entered, the first close back above line X by LEAVE_BUFFER_PP (2 pp)
A replay of 10 years (QQQ tiers 12/18/25%) gives enter t1/t2/t3 = 7/4/2, the same tier episodes as the history
table, about 4 alerts a year (max 10); a plain 0.5 pp hysteresis gave 12 a year (max 29), too noisy.
The homepage banner shows the current zone (no memory). Reminder only: no orders, no threshold or allocation change.
"""
from __future__ import annotations

ORDER = ["normal", "near", "t1", "t2", "t3"]
NEAR_PP = 0.02
LEAVE_BUFFER_PP = 0.02
NEW_HIGH_EPS = 1e-4
LABEL_ZH = {"normal": "正常", "near": "接近一级", "t1": "一级", "t2": "二级", "t3": "三级"}


def thresholds(tiers):
    t1, t2, t3 = float(tiers["t1"]), float(tiers["t2"]), float(tiers["t3"])
    return {"near": round(max(0.0, t1 - NEAR_PP), 6), "t1": t1, "t2": t2, "t3": t3}


def zone(loss, tiers):
    """loss = -drawdown (0.12 means 12% below the ATH). The current zone, for display."""
    th = thresholds(tiers)
    z = "normal"
    for s in ("near", "t1", "t2", "t3"):
        if loss >= th[s]:
            z = s
    return z


def ath_of(close, drawdown):
    if close is None or drawdown is None or drawdown <= -1:
        return None
    return float(close) / (1.0 + float(drawdown))


def trigger_prices(close, drawdown, tiers):
    ath = ath_of(close, drawdown)
    return {} if ath is None else {k: round(ath * (1.0 - v), 2) for k, v in thresholds(tiers).items()}


MAX_ATH_STEP = 0.15      # a new ATH more than 15% above the cycle's ATH in one step is not trusted as a new cycle


def cycle_id(sym, ath):
    return f"{sym}@{float(ath):.4f}" if ath is not None else None


def new_cycle_check(prev_ath, ath):
    """'same' | 'new' | 'suspect'. Only a validated ATH that rises by a plausible step starts a new cycle; a jump
    (split / adjustment / data repair artefact) is 'suspect' -> cannot judge, the old cycle is kept."""
    if prev_ath is None:
        return "new"
    if ath is None or ath <= float(prev_ath) * (1 + NEW_HIGH_EPS):
        return "same"
    return "new" if ath <= float(prev_ath) * (1 + MAX_ATH_STEP) else "suspect"


def advance(prev, loss, ath, tiers):
    """prev = {'cycle_ath': float|None, 'sent': [...]} per asset; 'sent' holds one 'enter:<line>' / 'leave:<line>'
    flag per line for the current cycle. Returns (new_state, events) with events like ('enter','t1') /
    ('leave','t1'). Leaving a line never re-arms its 'enter' alert in the same cycle; only a confirmed new ATH
    (new_cycle_check == 'new') starts a new cycle and re-arms every line."""
    prev = prev or {}
    cyc = prev.get("cycle_ath")
    sent = set(prev.get("sent") or [])
    if new_cycle_check(cyc, ath) == "new":
        cyc, sent = ath, set()
    th = thresholds(tiers)
    events = []
    for s in ("near", "t1", "t2", "t3"):
        if loss >= th[s] and f"enter:{s}" not in sent:
            sent.add(f"enter:{s}"); events.append(("enter", s))
    for s in ("t3", "t2", "t1"):
        if f"enter:{s}" in sent and f"leave:{s}" not in sent and loss < th[s] - LEAVE_BUFFER_PP:
            sent.add(f"leave:{s}"); events.append(("leave", s))
    return {"cycle_ath": cyc, "sent": sorted(sent), "zone": zone(loss, tiers)}, events


MAX_DAY_MOVE = 0.25      # |close/prev_close-1| above this (CP-01 holds at most 2x ETFs) -> unexplained jump


def _finite_pos(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return False
    return x > 0 and x == x and x != float("inf")


def row_inputs(row, tiers):
    """(loss, ath, reason). loss None means cannot judge (never a default zone)."""
    row = row or {}
    dd = row.get("strategy_drawdown")
    if not tiers:
        return None, None, "no_tiers"
    if dd is None or row.get("ath_is_true") is not True or row.get("ath_validation") != "PASS":
        return None, None, "ath_unvalidated"
    if not _finite_pos(row.get("close")):
        return None, None, "close_invalid"
    try:
        dd = float(dd)
    except (TypeError, ValueError):
        return None, None, "drawdown_invalid"
    if not (-1 < dd <= 1e-9):
        return None, None, "drawdown_out_of_range"
    pc = row.get("prev_close")
    if _finite_pos(pc) and abs(float(row["close"]) / float(pc) - 1) > MAX_DAY_MOVE:
        return None, None, "price_jump_unexplained"
    return -dd, ath_of(row.get("close"), dd), "ok"
