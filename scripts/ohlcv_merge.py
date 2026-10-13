#!/usr/bin/env python3
"""Fail-closed daily OHLCV merge rules (#133 6117657723; tasks D-05 / D-06). Pure functions, wired into
local_history_agent.append_latest (data-collection universe; site data first, free Yahoo fallback with basis check).

Replaces the current `local_history_agent.dashboard_bar` behaviour (which back-fills open/high/low with the close
when a row has only a close — the source of TQQQ's synthetic flat bars) once P0-05 is verified:
  - a bar is accepted only with real open, high, low, close (volume may be 0) and a finalized session date
    (≤ the expected latest completed NYSE session; never today's intraday value);
  - close-only rows are reported as `close_only` and NOT written as a full bar;
  - a date already in history with identical values is `unchanged` (idempotent re-runs);
  - a date already in history with different values is `conflict` and quarantined — never silently overwritten;
  - OHLC inconsistencies and extreme gaps (> 60 %, likely split/raw mix) are quarantined;
  - a symbol with no row from any source is `missing` (stale), never filled with the previous close.
Migration (after P0-05): local_history_agent.append_latest calls `normalize_bar` + `merge_bar` for every symbol of
research/audit/symbol_registry.json data_collection_universe, preferring sources that carry full OHLC
(docs/data.json stocks.*); core/index close-only rows stay close_only. Existing flat bars are fixed only through the
logged replacement path (data/history/corrections.jsonl) with an independent source, e.g. the owner pack.
"""
from __future__ import annotations
from datetime import date

FIELDS = ("open", "high", "low", "close")


def normalize_bar(row, expected_session):
    """row: dict with date/open/high/low/close/volume (any may be missing). Returns (status, bar_or_reason)."""
    if not isinstance(row, dict):
        return "missing", "no row"
    d = str(row.get("date") or "")[:10]
    try:
        day = date.fromisoformat(d)
    except ValueError:
        return "invalid", "bad date"
    if day > date.fromisoformat(str(expected_session)):
        return "not_final", f"{d} is after the latest completed session {expected_session}"
    if row.get("close") is None:
        return "missing", "no close"
    if any(row.get(k) is None for k in ("open", "high", "low")):
        return "close_only", {"date": d, "close": float(row["close"])}
    try:
        o, h, l, c = (float(row[k]) for k in FIELDS)
        v = float(row.get("volume") or 0)
    except (TypeError, ValueError):
        return "invalid", "non-numeric OHLC"
    if min(o, h, l, c) <= 0 or not (l <= min(o, c) <= max(o, c) <= h):
        return "invalid", "ohlc_inconsistent"
    return "ok", {"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v}


def merge_bar(history, status, bar, max_gap=0.60):
    """history: dict date -> (o, h, l, c, v). Returns (result, history_after). Never mutates the input."""
    if status != "ok":
        return {"result": status, "detail": bar}, history
    d = bar["date"]
    new = (bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
    if d in history:
        old = history[d]
        if all(abs(a - b) <= 1e-9 * max(1.0, abs(a)) for a, b in zip(old[:4], new[:4])):
            return {"result": "unchanged", "date": d}, history
        return {"result": "conflict", "date": d, "old": old[:4], "new": new[:4],
                "action": "quarantined; correct only via data/history/corrections.jsonl with an independent source"}, history
    prev = [k for k in history if k < d]
    if prev:
        last_close = history[max(prev)][3]
        if last_close > 0 and abs(bar["close"] / last_close - 1) > max_gap:
            return {"result": "quarantined", "date": d, "reason": "extreme_gap_check"}, history
    out = dict(history)
    out[d] = new
    return {"result": "appended", "date": d}, out
