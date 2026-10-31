#!/usr/bin/env python3
"""Core-ETF drawdown tier alerts: Telegram on tier changes + public state for the homepage banner.

Data trust: the core rows must be the latest completed NYSE session (Daily runs before Server Action Watch,
so the server snapshot cannot be used here); a stale or unvalidated row is 'cannot judge', never a zone.
Owner-approved #133 6516033003 (10/30) and 6537316711 (10/31): alert when a CP-01 asset first comes within 2 pp
of tier 1, enters a tier, or recovers back out of a tier; once per line per drawdown cycle (see core_tier_state).
When data cannot be trusted: one 'cannot judge' message, state kept, no trigger alert. Separate from the playbook
alert switch (MYALPHA_PLAYBOOK_ALERTS_ENABLED stays off). Reminder only: no orders, no threshold, rule or
allocation change. Reads docs/data.json, config/playbooks.public.json, docs/research/server_action_status.json.
Writes docs/research/core_tier_alert_status.json (no positions, no amounts).
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import core_tier_state as cts  # noqa: E402
import trading_calendar as tc  # noqa: E402

DATA = ROOT / "docs" / "data.json"
CONFIG = ROOT / "config" / "playbooks.public.json"
SERVER = ROOT / "docs" / "research" / "server_action_status.json"
OUT = ROOT / "docs" / "research" / "core_tier_alert_status.json"
VERSION = "cta-1.0"
EVENTS_KEEP = 40
MAX_SEND_ATTEMPTS = 3   # a failed delivery is retried on later runs, at most this many attempts in total
DISCLAIMER = "这是提醒，不是买卖指令；是否加仓由你决定。"


def _load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def notify(text):
    if os.getenv("CORE_TIER_ALERTS_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return "disabled"
    from daily_guardian import send_telegram
    return send_telegram(text)


def message(sym, kind, line, row, tiers, as_of):
    dd = float(row.get("strategy_drawdown"))
    th, px = cts.thresholds(tiers), cts.trigger_prices(row.get("close"), dd, tiers)
    if kind == "enter" and line == "near":
        head = f"{sym} 接近一级加仓线（距一级不到 {cts.NEAR_PP:.0%}）"
        ref = "t1"
    elif kind == "enter":
        head, ref = f"{sym} 进入{cts.LABEL_ZH[line]}加仓线", line
    else:
        head, ref = f"{sym} 回升，已离开{cts.LABEL_ZH[line]}加仓线", line
    return (f"MyAlpha｜核心ETF回撤分档：{head}\n"
            f"当前回撤（距历史最高）{dd:.1%}；{cts.LABEL_ZH[ref]}阈值 {th[ref]:.0%}，对应价格 ≈ {px.get(ref, '—')}。"
            f"一/二/三级 = {th['t1']:.0%}/{th['t2']:.0%}/{th['t3']:.0%}。数据日期 {as_of}，数据可信。\n{DISCLAIMER}")


def _deliver(item, send):
    """Send one outbox item; status 'sent' is terminal; failures are retried on later runs up to MAX_SEND_ATTEMPTS."""
    d = send(item["text"])
    item["attempts"] = int(item.get("attempts") or 0) + 1
    item["status"] = "sent" if d == "sent" else ("disabled" if d in ("disabled", "not_configured") else "failed")
    item["last_delivery"] = d
    return d


def build(now=None, send=notify, data=None, config=None, server=None, previous=None):
    now = now or datetime.now(timezone.utc)
    data = data if data is not None else _load(DATA, {})
    config = config if config is not None else _load(CONFIG, {})
    server = server if server is not None else _load(SERVER, {})
    previous = previous if previous is not None else _load(OUT, {})
    tiers_all = config.get("core_tiers") or {}
    assets = next((p.get("assets") for p in config.get("playbooks") or [] if p.get("playbook_id") == "CP-01"), None) or []
    expected = str(tc.expected_latest_completed_session(now))
    trust = (server or {}).get("data_trust") or {}
    server_bad = trust.get("ok") is False and trust.get("market_as_of") == expected   # same-session explicit failure
    prev_syms = (previous or {}).get("symbols") or {}
    events = list((previous or {}).get("events") or [])
    # outbox: idempotency key -> item; a key is sent at most once; failed items retry on later runs
    outbox = {o["key"]: dict(o) for o in (previous or {}).get("outbox") or [] if o.get("key")}
    deliveries = []
    for item in outbox.values():
        if item.get("status") == "failed" and int(item.get("attempts") or 0) < MAX_SEND_ATTEMPTS:
            deliveries.append(_deliver(item, send))

    def emit(key, text, event):
        if key in outbox:                       # idempotent: the same alert is never queued twice
            return
        item = {"key": key, "text": text, "created_at": now.isoformat(), "attempts": 0}
        outbox[key] = item
        deliveries.append(_deliver(item, send))
        events.append({**event, "at": now.isoformat(), "key": key, "delivery": item["last_delivery"]})

    out_syms = {}
    for sym in assets:
        row = ((data or {}).get("core") or {}).get(sym) or {}
        tiers = tiers_all.get(sym)
        before = prev_syms.get(sym) or {}
        as_of = row.get("date")
        if server_bad:
            loss, ath, reason = None, None, "data_trust_not_ok"
        elif as_of != expected:
            loss, ath, reason = None, None, f"stale_data({as_of}!={expected})"
        else:
            loss, ath, reason = cts.row_inputs(row, tiers)
            if loss is not None and cts.new_cycle_check(before.get("cycle_ath"), ath) == "suspect":
                loss, reason = None, "ath_jump_unverified"
        audit = {"as_of": as_of, "expected_session": expected, "close": row.get("close"),
                 "drawdown": row.get("strategy_drawdown"), "ath_implied": ath,
                 "ath_validation": row.get("ath_validation"), "price_basis": "validated ATH (Yahoo high), close"}
        if loss is None:
            rec = {**{k: before.get(k) for k in ("cycle_ath", "cycle_id", "sent", "zone")},
                   "judgment": "cannot_judge", "reason": reason, **audit}
            if before.get("judgment") != "cannot_judge":
                emit(f"{sym}|cannot_judge|{as_of}|{reason}",
                     f"MyAlpha｜核心ETF回撤分档：{sym} 暂不能判断（{reason}），数据日期 {as_of or '—'}。"
                     f"恢复可信数据前不会发出加仓线提醒。",
                     {"symbol": sym, "kind": "cannot_judge", "reason": reason})
        else:
            state, evs = cts.advance(before, loss, ath, tiers)
            cid = cts.cycle_id(sym, state["cycle_ath"])
            for kind, line in evs:
                emit(f"{cid}|{kind}:{line}", message(sym, kind, line, row, tiers, as_of),
                     {"symbol": sym, "kind": kind, "line": line, "cycle_id": cid,
                      "drawdown": row.get("strategy_drawdown"), "as_of": as_of})
            rec = {**state, "cycle_id": cid, "judgment": "evaluated", "reason": "ok", **audit,
                   "thresholds": cts.thresholds(tiers),
                   "trigger_prices": cts.trigger_prices(row.get("close"), row.get("strategy_drawdown"), tiers)}
        out_syms[sym] = rec
    keep = sorted(outbox.values(), key=lambda o: o.get("created_at") or "")[-EVENTS_KEEP:]
    return {"version": VERSION, "generated_at": now.isoformat(), "policy": "reminder_only_no_orders",
            "near_pp": cts.NEAR_PP, "leave_buffer_pp": cts.LEAVE_BUFFER_PP, "expected_session": expected,
            "symbols": out_syms, "events": events[-EVENTS_KEEP:], "outbox": keep, "last_deliveries": deliveries}


def main():
    out = build()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    zones = {s: (v.get("zone") or "—") + ("" if v["judgment"] == "evaluated" else "?") for s, v in out["symbols"].items()}
    print(f"::notice title=CORE_TIER::{json.dumps(zones, ensure_ascii=False)} deliveries={out['last_deliveries']}")


if __name__ == "__main__":
    main()
