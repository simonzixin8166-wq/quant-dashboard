#!/usr/bin/env python3
"""Threshold ledger and review (Owner 2026-11-15: record every time a threshold is reached, with the values, dates
and counts, and review it). Reminder/record only: never changes a threshold, a position or an alert.

What it records (append-only, research/archive/):
  threshold_daily.jsonl   one row per core ETF per session from DAILY_FROM: close, ATH (running max high), drawdown,
                          zone and the gap to every line (pp and price). A later price revision appends a
                          'revision' row; stored rows are never rewritten.
  threshold_events.jsonl  'transition' rows: every enter/leave of a line, replayed from prices with the production
                          rule (core_tier_state.advance: once per line per cycle, leave at line - 2 pp, near has no
                          leave). Rows before LIVE_FROM are tagged historical_replay (not forward evidence).
                          'alert' rows: every alert core_tier_alert actually sent (its status file keeps only 40).
What it reviews (docs/research/threshold_review.json, recomputed each run, descriptive only):
  per asset: current zone and gaps; live transitions; every crossing of a line even when no alert fires (and
  sessions within 0.5 pp of an unreached line); sessions spent in each zone; every episode (enter date and values, sessions in the zone,
  deepest drawdown and its date, how it ended); +5/+20/+60-session return and worst low after each entry;
  historical counts and medians (historical replay, never mixed with live); alert reconciliation (each sent alert
  supported by prices or not, transitions without an alert, delay after the close); shock-event thresholds and the
  turning-point checklist counts.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import core_tier_state as cts  # noqa: E402

ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
CONFIG = ROOT / "config" / "playbooks.public.json"
ALERT_STATUS = ROOT / "docs" / "research" / "core_tier_alert_status.json"
SHOCKS = ROOT / "research" / "archive" / "shock_events.jsonl"
TURNING = ROOT / "research" / "archive" / "turning_point_observations.jsonl"
DAILY = ROOT / "research" / "archive" / "threshold_daily.jsonl"
EVENTS = ROOT / "research" / "archive" / "threshold_events.jsonl"
OUT = ROOT / "docs" / "research" / "threshold_review.json"

VERSION = "threshold-ledger-1.0"
DAILY_FROM = "2026-10-01"
LIVE_FROM = "2026-11-02"       # first session core_tier_alert evaluated (alert as_of 2026-11-02)
FOLLOW = (5, 20, 60)
REVISION_TOL = 0.001
PUBLISHED_TOL = 0.005          # published drawdown vs recomputed, 0.5 pp
LINES = ("near", "t1", "t2", "t3")


def r6(x):
    return None if x is None else round(float(x), 6)


def read_prices(path=ARCHIVE, symbols=None):
    """{SYM: [(date_str, high, low, close), ...]} sorted, from the canonical Stooq archive (same parsing rules as
    local_history_agent.read_archive: positive OHLC, last row wins per date)."""
    out = {}
    if not Path(path).exists():
        return out
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            base = Path(name).name.lower()
            if name.startswith("__MACOSX/") or not base.endswith("_us_d.csv"):
                continue
            sym = base[: -len("_us_d.csv")].upper()
            if symbols and sym not in symbols:
                continue
            rows = {}
            for r in csv.DictReader(io.StringIO(z.read(name).decode("utf-8", "replace"))):
                r = {str(k).strip().lower(): v for k, v in r.items()}
                try:
                    d = str(r["date"])[:10]
                    o, hi, lo, c = (float(r[k]) for k in ("open", "high", "low", "close"))
                except (KeyError, TypeError, ValueError):
                    continue
                if min(o, hi, lo, c) > 0:
                    rows[d] = (d, hi, lo, c)
            out[sym] = [rows[d] for d in sorted(rows)]
    return out


def replay(bars, tiers):
    """Daily states and transitions with the production rule. ATH = running max of the daily high."""
    th = cts.thresholds(tiers)
    state, ath, days, trans = {}, None, [], []
    for d, hi, lo, c in bars:
        ath = hi if ath is None else max(ath, hi)
        loss = max(0.0, 1.0 - c / ath)
        if state.get("cycle_ath") is not None and ath > state["cycle_ath"] * (1 + cts.NEW_HIGH_EPS):
            state = {}      # a traded new high: new cycle (the live 'suspect' step guard is for published ATHs)
        state, evs = cts.advance(state, loss, ath, tiers)
        gaps = {s: {"line": th[s], "price": round(ath * (1 - th[s]), 2), "gap_pp": round((th[s] - loss) * 100, 2)}
                for s in LINES}
        days.append({"date": d, "close": c, "high": hi, "low": lo, "ath": ath, "loss": loss,
                     "zone": state["zone"], "cycle_ath": state["cycle_ath"], "gaps": gaps})
        for kind, line in evs:
            trans.append({"date": d, "kind": kind, "line": line, "line_value": th[line], "close": c,
                          "ath": round(ath, 4), "cycle_ath": round(state["cycle_ath"], 4), "drawdown": r6(-loss),
                          "line_price": gaps[line]["price"]})
    return days, trans


def episodes(days, trans, tiers):
    """One episode per 'enter' transition: until its 'leave' (t1-t3) or the next cycle (near / never left)."""
    th = cts.thresholds(tiers)
    idx = {d["date"]: i for i, d in enumerate(days)}
    out = []
    for t in trans:
        if t["kind"] != "enter":
            continue
        i0, line = idx[t["date"]], t["line"]
        cyc = days[i0]["cycle_ath"]
        end, how = None, "open"
        for tt in trans:
            if tt["date"] > t["date"] and tt["kind"] == "leave" and tt["line"] == line and tt["cycle_ath"] == round(cyc, 4):
                end, how = idx[tt["date"]], "left"
                break
        if end is None:
            for j in range(i0 + 1, len(days)):
                if days[j]["cycle_ath"] != cyc:
                    end, how = j, "new_ath"
                    break
        span = days[i0: (end if end is not None else len(days))]
        deep = max(span, key=lambda x: x["loss"])
        e = {"line": line, "line_value": th[line], "enter_date": t["date"], "enter_close": round(t["close"], 4),
             "enter_drawdown": t["drawdown"], "cycle_ath": t["cycle_ath"],
             "sessions_in_zone": sum(1 for x in span if x["loss"] >= th[line]), "sessions_to_end": len(span),
             "deepest_drawdown": r6(-deep["loss"]), "deepest_date": deep["date"], "deepest_close": round(deep["close"], 4),
             "end": how, "end_date": days[end]["date"] if end is not None else None}
        for h in FOLLOW:
            j = i0 + h
            if j < len(days):
                lows = [x["low"] for x in days[i0 + 1: j + 1]]
                e[f"ret_{h}"] = r6(days[j]["close"] / t["close"] - 1)
                e[f"mae_{h}"] = r6(min(lows) / t["close"] - 1)
            else:
                e[f"ret_{h}"] = e[f"mae_{h}"] = None
        out.append(e)
    return out


def _med(xs):
    xs = [x for x in xs if x is not None]
    return r6(median(xs)) if xs else None


NEAR_MISS_PP = 0.5


def touches(days, tiers, since):
    """Every close that crosses a line, whether or not an alert fires (alerts are once per cycle; a re-touch after
    leaving is still an occurrence). cross_in = loss goes from below the line to at/beyond it; cross_out = back
    above it. near_miss = a session within NEAR_MISS_PP of a line that was not reached."""
    th = cts.thresholds(tiers)
    live = {s: [] for s in LINES}
    hist = Counter()
    miss = {s: [] for s in LINES}
    for a, b in zip(days, days[1:]):
        for s in LINES:
            kind = "cross_in" if a["loss"] < th[s] <= b["loss"] else "cross_out" if b["loss"] < th[s] <= a["loss"] else None
            if kind and b["date"] >= since:
                live[s].append({"date": b["date"], "kind": kind, "drawdown": r6(-b["loss"]), "close": round(b["close"], 4),
                                "line_price": b["gaps"][s]["price"]})
            elif kind == "cross_in":
                hist[s] += 1
            if b["date"] >= since and 0 < (th[s] - b["loss"]) * 100 <= NEAR_MISS_PP:
                miss[s].append({"date": b["date"], "gap_pp": b["gaps"][s]["gap_pp"], "close": round(b["close"], 4)})
    return {s: {"cross_in": sum(1 for x in live[s] if x["kind"] == "cross_in"),
                "cross_out": sum(1 for x in live[s] if x["kind"] == "cross_out"),
                "events": live[s], "near_misses": miss[s], "historical_cross_in": hist[s]} for s in LINES}


def stats(eps):
    by = defaultdict(list)
    for e in eps:
        by[e["line"]].append(e)
    out = {}
    for line in LINES:
        es = by.get(line, [])
        s = {"entries": len(es), "years": sorted({e["enter_date"][:4] for e in es}),
             "median_sessions_in_zone": _med([e["sessions_in_zone"] for e in es]),
             "median_deepest_drawdown": _med([e["deepest_drawdown"] for e in es]),
             "deepest_ever": min((e["deepest_drawdown"] for e in es), default=None)}
        for h in FOLLOW:
            rs = [e[f"ret_{h}"] for e in es if e[f"ret_{h}"] is not None]
            s[f"n_{h}"] = len(rs)
            s[f"median_ret_{h}"] = _med(rs)
            s[f"positive_{h}"] = f"{sum(1 for x in rs if x > 0)}/{len(rs)}" if rs else None
            s[f"median_mae_{h}"] = _med([e[f"mae_{h}"] for e in es])
        out[line] = s
    return out


def read_jsonl(p):
    p = Path(p)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_jsonl(p, rows):
    if not rows:
        return
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def daily_rows(sym, days, stored, published, now_iso):
    """New rows (and revision rows) for threshold_daily.jsonl."""
    last = {}
    for r in stored:
        if r.get("symbol") == sym:
            last[r["date"]] = r
    out = []
    for d in days:
        if d["date"] < DAILY_FROM:
            continue
        row = {"type": "snapshot", "symbol": sym, "date": d["date"], "close": round(d["close"], 4),
               "ath": round(d["ath"], 4), "drawdown": r6(-d["loss"]), "zone": d["zone"],
               "gaps": d["gaps"], "recorded_at": now_iso}
        pub = published.get(sym)
        if pub and pub.get("as_of") == d["date"] and pub.get("drawdown") is not None:
            row["published_drawdown"] = r6(pub["drawdown"])
            row["published_ath"] = r6(pub.get("ath_implied"))
            row["published_mismatch"] = abs(float(pub["drawdown"]) + d["loss"]) > PUBLISHED_TOL
        old = last.get(d["date"])
        if old is None:
            out.append(row)
        elif abs(old["close"] / row["close"] - 1) > REVISION_TOL or abs(old["ath"] / row["ath"] - 1) > REVISION_TOL:
            out.append({**row, "type": "revision", "revises": {"close": old["close"], "ath": old["ath"]}})
        elif pub and pub.get("as_of") == d["date"] and "published_drawdown" not in old \
                and not any(x.get("type") == "published" and x["date"] == d["date"] for x in stored if x.get("symbol") == sym):
            out.append({"type": "published", "symbol": sym, "date": d["date"], "recorded_at": now_iso,
                        **{k: row[k] for k in ("published_drawdown", "published_ath", "published_mismatch")},
                        "drawdown": row["drawdown"]})
    return out


def transition_key(sym, t):
    return f"{sym}|{t['date']}|{t['kind']}:{t['line']}"


def alert_rows(status, stored_keys, now_iso):
    out = []
    for e in (status or {}).get("events") or []:
        k = f"alert|{e.get('key')}"
        if e.get("key") and k not in stored_keys:
            out.append({"type": "alert", "key": k, "symbol": e.get("symbol"), "kind": e.get("kind"),
                        "line": e.get("line"), "as_of": e.get("as_of"), "at": e.get("at"),
                        "cycle_id": e.get("cycle_id"), "drawdown": r6(e.get("drawdown")),
                        "delivery": e.get("delivery"), "recorded_at": now_iso})
            stored_keys.add(k)
    return out


def _close_utc(d):
    """Approximate NYSE close (16:00 New York) in UTC: 21:00Z in winter (Nov-Mar), 20:00Z otherwise."""
    y, m, dd = (int(x) for x in d.split("-"))
    winter = m in (11, 12, 1, 2, 3)
    return datetime(y, m, dd, 21 if winter else 20, tzinfo=timezone.utc)


def reconcile(alerts, trans_by_sym, days_by_sym, alerted):
    """alerted = the assets core_tier_alert watches (CP-01); the other core ETFs are recorded but never alerted."""
    unsupported, matched, delays = [], 0, []
    live_trans = {(s, t["date"], t["kind"], t["line"]) for s, ts in trans_by_sym.items() if s in alerted
                  for t in ts if t["date"] >= LIVE_FROM}
    seen = set()
    for a in sorted(alerts, key=lambda a: (a.get("as_of") or "", a.get("at") or "")):
        k = (a["symbol"], a["as_of"], a["kind"], a["line"])
        if a.get("at") and a.get("as_of"):
            try:
                at = datetime.fromisoformat(a["at"].replace("Z", "+00:00"))
                delays.append(round((at - _close_utc(a["as_of"])).total_seconds() / 3600, 1))
            except ValueError:
                pass
        if k in live_trans:
            matched += 1
            seen.add(k)
            continue
        day = next((d for d in days_by_sym.get(a["symbol"], []) if d["date"] == a["as_of"]), None)
        unsupported.append({"symbol": a["symbol"], "as_of": a["as_of"], "alert": f"{a['kind']}:{a['line']}",
                            "alert_drawdown": a.get("drawdown"), "alert_cycle_id": a.get("cycle_id"), "sent_at": a.get("at"),
                            "price_drawdown": r6(-day["loss"]) if day else None,
                            "price_ath": round(day["ath"], 4) if day else None, "price_zone": day["zone"] if day else None})
    missed = [{"symbol": s, "date": d, "transition": f"{kd}:{ln}"} for (s, d, kd, ln) in sorted(live_trans - seen)]
    return {"scope": sorted(alerted), "alerts": len(alerts), "matched": matched, "unsupported_by_prices": unsupported,
            "transitions_without_alert": missed,
            "delay_hours_after_close": {"n": len(delays), "median": _med(delays), "max": max(delays) if delays else None}}


def shock_summary(rows):
    """Shock-event thresholds (config/shock_watch.json) after their append-only corrections."""
    import shock_event_monitor as sem
    corr = defaultdict(list)
    for r in rows:
        if r.get("type") == "correction":
            corr[r.get("event_id")].append(r)
    ev = [sem.apply_corrections(r, corr.get(r.get("event_id"))) for r in rows if r.get("type") == "event"]
    kept = [e for e in ev if not e.get("retracted")]
    return {"events": len(ev), "retracted": len(ev) - len(kept), "corrected": sum(1 for e in ev if e.get("corrections")),
            "by_subject": dict(Counter(e.get("subject") for e in kept).most_common()),
            "by_severity": dict(Counter(e.get("severity") for e in kept).most_common()),
            "price_triggers": sum(1 for e in kept if e.get("price_trigger")),
            "news_triggers": sum(1 for e in kept if e.get("news_trigger")),
            "vix_triggers": sum(1 for e in kept if e.get("vix_trigger")),
            "list": [{"event_id": e.get("event_id"), "subject": e.get("subject"), "ref_session": e.get("ref_session"),
                      "severity": e.get("severity"), "price_trigger": e.get("price_trigger"),
                      "news_trigger": e.get("news_trigger"), "first_seen": e.get("first_seen"),
                      "retracted": bool(e.get("retracted")), "corrections": len(e.get("corrections") or [])} for e in ev]}


def turning_summary(rows):
    rows = sorted(rows, key=lambda r: r.get("market_date") or "")
    first_met, met_days = {}, Counter()
    for r in rows:
        for k, v in (r.get("statuses") or {}).items():
            if v == "met":
                met_days[k] += 1
                first_met.setdefault(k, r["market_date"])
    return {"sessions": len(rows), "trigger_sessions": sum(1 for r in rows if r.get("trigger")),
            "max_met": max((r.get("met", 0) for r in rows), default=None),
            "met_sessions_by_condition": dict(met_days), "first_met": first_met,
            "latest": rows[-1] if rows else None}


def build(prices, tiers_cfg, status, shocks, turning, stored_daily, stored_events, now=None, alerted=()):
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    published = (status or {}).get("symbols") or {}
    keys = {r.get("key") for r in stored_events}
    new_daily, new_events, syms = [], [], {}
    trans_by, days_by = {}, {}
    for sym in sorted(tiers_cfg):
        bars = prices.get(sym)
        if not bars:
            syms[sym] = {"status": "unavailable", "reason": "no_price_history"}
            continue
        tiers = tiers_cfg[sym]
        days, trans = replay(bars, tiers)
        trans_by[sym], days_by[sym] = trans, days
        new_daily += daily_rows(sym, days, stored_daily, published, now_iso)
        for t in trans:
            k = transition_key(sym, t)
            if k not in keys:
                basis = "historical_replay" if t["date"] < LIVE_FROM else "live_period"
                new_events.append({"type": "transition", "key": k, "symbol": sym, "basis": basis, **t,
                                   "recorded_at": now_iso})
                keys.add(k)
        eps = episodes(days, trans, tiers)
        live_eps = [e for e in eps if e["enter_date"] >= LIVE_FROM]
        hist_eps = [e for e in eps if e["enter_date"] < LIVE_FROM]
        cur = days[-1]
        nxt = next((s for s in LINES if cur["loss"] < cts.thresholds(tiers)[s]), None)
        syms[sym] = {
            "thresholds": cts.thresholds(tiers),
            "current": {"date": cur["date"], "close": round(cur["close"], 4), "ath": round(cur["ath"], 4),
                        "drawdown": r6(-cur["loss"]), "zone": cur["zone"], "zone_zh": cts.LABEL_ZH[cur["zone"]],
                        "next_line": nxt, "gaps": cur["gaps"]},
            "live": {"from": LIVE_FROM, "transitions": [t for t in trans if t["date"] >= LIVE_FROM],
                     "episodes": live_eps, "touches": touches(days, tiers, LIVE_FROM),
                     "sessions_by_zone": dict(Counter(d["zone"] for d in days if d["date"] >= LIVE_FROM)),
                     "counts": dict(Counter(f"{t['kind']}:{t['line']}" for t in trans if t["date"] >= LIVE_FROM))},
            "historical_replay": {"from": bars[0][0], "to": max((t["date"] for t in trans if t["date"] < LIVE_FROM), default=None),
                                  "stats": stats(hist_eps), "episodes": len(hist_eps),
                                  "note_zh": "历史重建，不是前瞻证据；只作描述，不作规则依据"},
        }
    alerts = [r for r in stored_events if r.get("type") == "alert"]
    new_alerts = alert_rows(status, keys, now_iso)
    new_events += new_alerts
    alerts += new_alerts
    stale = sorted(r["key"] for r in stored_events if r.get("type") == "transition"
                   and r["key"] not in {transition_key(s, t) for s, ts in trans_by.items() for t in ts}
                   and r.get("symbol") in trans_by)
    review = {
        "version": VERSION, "generated_at": now_iso, "policy": "record_and_review_only_no_orders_no_threshold_change",
        "rule": "core_tier_state.advance: once per line per cycle; leave at line - 2 pp; near = t1 - 2 pp; ATH = running max high",
        "live_from": LIVE_FROM, "symbols": syms,
        "alert_reconciliation": reconcile(alerts, trans_by, days_by, set(alerted) or set(published)),
        "transitions_no_longer_supported": stale,
        "published_mismatches": [{"symbol": r["symbol"], "date": r["date"], "published": r.get("published_drawdown"),
                                  "prices": r.get("drawdown")}
                                 for r in stored_daily + new_daily if r.get("published_mismatch")],
        "shock_events": shock_summary(shocks),
        "turning_point_checklist": turning_summary(turning),
        "note_zh": "阈值记录与复盘：只记录和描述，不改阈值、不下单。实时期从 2026-11-02 起；之前是历史重建，单独统计。",
    }
    return review, new_daily, new_events


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    tiers = cfg.get("core_tiers") or {}
    prices = read_prices(symbols=set(tiers))
    status = json.loads(ALERT_STATUS.read_text(encoding="utf-8")) if ALERT_STATUS.exists() else {}
    alerted = next((p.get("assets") for p in cfg.get("playbooks") or [] if p.get("playbook_id") == "CP-01"), None) or []
    review, nd, ne = build(prices, tiers, status, read_jsonl(SHOCKS), read_jsonl(TURNING), read_jsonl(DAILY),
                           read_jsonl(EVENTS), alerted=alerted)
    append_jsonl(DAILY, nd)
    append_jsonl(EVENTS, ne)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rec = review["alert_reconciliation"]
    print(json.dumps({"daily_rows": len(nd), "event_rows": len(ne), "alerts": rec["alerts"], "matched": rec["matched"],
                      "unsupported": len(rec["unsupported_by_prices"]), "without_alert": len(rec["transitions_without_alert"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
