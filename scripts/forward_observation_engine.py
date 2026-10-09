#!/usr/bin/env python3
"""Server-side forward observation ledger (independent of anyone opening the website).

Runs inside the Daily workflow right after docs/data.json is rebuilt. For the latest completed NYSE
session it records one immutable observation per covered watchlist symbol, using only public inputs
(the published trend_pulse / daily closes / market indicators). Nothing private is read or written.

Ledger  : research/archive/forward_observations.jsonl   (append-only; one JSON object per line)
Status  : docs/research/forward_observation_status.json (derived; safe to regenerate)

Guarantees
- event_id = sha256(session|symbol|rule_hash)[:24]; re-running the same session is a no-op (idempotent).
- Prior ledger lines are never rewritten or removed; check_append_only() compares with the committed
  version and the run fails if any earlier line changed or disappeared.
- captured_at is the server clock; attested_forward is true only when captured before the next
  session opened (09:30 ET), i.e. before any outcome information could exist.
- A session with no observation stays an explicit GAP in the status file; nothing is backfilled as
  forward, and the statistics never silently restart.
- 20/60/120 horizons are NYSE trading sessions after the observation session (scripts/trading_calendar).
  Outcomes are read from later observations' own recorded closes; benchmark = QQQ over the same window.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

DATA = ROOT / "docs" / "data.json"
LEDGER = ROOT / "research" / "archive" / "forward_observations.jsonl"
STATUS = ROOT / "docs" / "research" / "forward_observation_status.json"
ET = ZoneInfo("America/New_York")
ENGINE_VERSION = "fo-1.0"
HORIZONS = (20, 60, 120)
BENCHMARK = "QQQ"

# Rule definition, mirrored from the browser journal (investment-assistant.js classify +
# stock-watchlist.js assistantCandidates + decision-journal.js candidateDecision) but evaluated on the
# completed daily close. Its hash is the rule version stored with every observation.
RULES = {
    "market_mode": [
        ["panic", {"ixic_le": -0.04, "spx_le": -0.035, "vix_ge": 35}],
        ["fear", {"ixic_le": -0.025, "spx_le": -0.02, "vix_ge": 28}],
        ["watch", {"ixic_le": -0.015, "spx_le": -0.0125, "vix_ge": 25}],
        ["greed", {"ixic_ge": 0.025, "spx_ge": 0.02, "vix_lt": 20}],
    ],
    "eligible_fear": "stage not in (趋势恶化,趋势退潮) and (score is null or score > -20)",
    "eligible_other": "score >= 75",
    "decision": [["退潮|恶化", "等待修复"], ["二次启动|启动|重新|修复中", "修复候选"],
                 ["@fear", "大跌机会候选"], ["钝化|高位", "高位观察"], ["*", "继续观察"]],
    "horizons_sessions": list(HORIZONS),
    "benchmark": BENCHMARK,
}
RULE_HASH = hashlib.sha256(json.dumps(RULES, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def num(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def market_mode(spx, ixic, vix):
    if (ixic is not None and ixic <= -0.04) or (spx is not None and spx <= -0.035) or (vix is not None and vix >= 35):
        return "fear", "panic"
    if (ixic is not None and ixic <= -0.025) or (spx is not None and spx <= -0.02) or (vix is not None and vix >= 28):
        return "fear", "fear"
    if (ixic is not None and ixic <= -0.015) or (spx is not None and spx <= -0.0125) or (vix is not None and vix >= 25):
        return "fear", "watch"
    if ((ixic is not None and ixic >= 0.025) or (spx is not None and spx >= 0.02)) and (vix is None or vix < 20):
        return "greed", "greed"
    return "normal", "normal"


def eligible(mode, stage, score):
    if mode == "fear":
        return stage not in ("趋势恶化", "趋势退潮") and (score is None or score > -20)
    return score is not None and score >= 75


def decision(stage, mode):
    import re
    if re.search("退潮|恶化", stage): return "等待修复"
    if re.search("二次启动|启动|重新|修复中", stage): return "修复候选"
    if mode == "fear": return "大跌机会候选"
    if re.search("钝化|高位", stage): return "高位观察"
    return "继续观察"


def next_open_utc(session: date) -> datetime:
    return datetime.combine(tc.next_session(session), time(9, 30), ET).astimezone(timezone.utc)


def event_id(session, symbol):
    return hashlib.sha256(f"{session}|{symbol}|{RULE_HASH}".encode()).hexdigest()[:24]


def read_ledger(path=LEDGER):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def build_observations(data, now_utc=None, source_sha=None, run_id=None):
    """Observations for the latest completed session in data.json, or ([], reason) when not eligible."""
    now_utc = now_utc or datetime.now(timezone.utc)
    tp = data.get("trend_pulse") or {}
    prices = {**(data.get("stocks") or {}), **(data.get("index") or {})}
    mi = data.get("market_indicators") or {}
    sessions = sorted({str(v.get("date"))[:10] for v in tp.values() if isinstance(v, dict) and v.get("available") and v.get("date")})
    if not sessions:
        return [], "no_trend_pulse"
    session = date.fromisoformat(sessions[-1])
    if not tc.is_session(session):
        return [], "not_a_session"
    if session > tc.expected_latest_completed_session(now_utc):
        return [], "session_not_completed"
    spx, ixic, vix = (num((mi.get(k) or {}).get("day_chg")) for k in ("spx", "ixic", "vix"))
    vix_level = num((mi.get("vix") or {}).get("close"))
    mode, level = market_mode(spx, ixic, vix_level)
    captured = now_utc.replace(microsecond=0)
    attested = captured < next_open_utc(session)
    rows = []
    for symbol in sorted(tp):
        t = tp[symbol] or {}
        if not t.get("available") or str(t.get("date"))[:10] != session.isoformat():
            continue
        px = prices.get(symbol) or {}
        close = num(px.get("close")) if str(px.get("date"))[:10] == session.isoformat() else None
        stage, score = str(t.get("state") or ""), num(t.get("score"))
        payload = {"stage": stage, "score": score, "close": close, "eligible": eligible(mode, stage, score),
                   "decision": decision(stage, mode)}
        rows.append({
            "event_id": event_id(session.isoformat(), symbol),
            "session": session.isoformat(), "symbol": symbol,
            "market": {"mode": mode, "level": level, "spx_chg": spx, "ixic_chg": ixic, "vix": vix_level},
            "payload": payload,
            "payload_sha": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16],
            "rule_hash": RULE_HASH, "engine": ENGINE_VERSION,
            "market_as_of": session.isoformat(), "captured_at": captured.isoformat().replace("+00:00", "Z"),
            "attested_forward": attested, "capture": "server_daily",
            "source_sha": source_sha, "run_id": run_id,
            "matures": {str(h): tc.add_sessions(session, h).isoformat() for h in HORIZONS},
        })
    return rows, "ok" if rows else "no_symbols"


def check_append_only(old_lines, new_lines):
    """Every previously committed line must still be present, unchanged and in order."""
    if len(new_lines) < len(old_lines):
        return False, "ledger_shrank"
    if new_lines[:len(old_lines)] != old_lines:
        return False, "prior_line_changed"
    return True, "ok"


def committed_lines(path=LEDGER):
    try:
        rel = path.relative_to(ROOT).as_posix()
        out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [x for x in out.splitlines() if x.strip()]
    except Exception:
        return []


def outcomes(rows):
    """Horizon outcomes from the ledger's own later closes (no extra data source, no price replay)."""
    close = {}
    for r in rows:
        c = (r.get("payload") or {}).get("close")
        if c is not None:
            close.setdefault((r["symbol"], r["session"]), c)
    out = []
    for r in rows:
        base = (r.get("payload") or {}).get("close")
        bench0 = close.get((BENCHMARK, r["session"]))
        for h in HORIZONS:
            md = r["matures"][str(h)]
            end, bend = close.get((r["symbol"], md)), close.get((BENCHMARK, md))
            if base is None or end is None:
                continue
            ret = end / base - 1
            excess = (ret - (bend / bench0 - 1)) if bench0 and bend else None
            out.append({"event_id": r["event_id"], "h": h, "matured_on": md, "ret": round(ret, 6),
                        "excess_vs_qqq": None if excess is None else round(excess, 6),
                        "attested_forward": bool(r.get("attested_forward"))})
    return out


def status(rows, today=None):
    today = today or datetime.now(timezone.utc).date()
    sessions = sorted({r["session"] for r in rows})
    gaps = []
    if sessions:
        gaps = [d.isoformat() for d in tc.sessions_between(date.fromisoformat(sessions[0]), tc.expected_latest_completed_session())
                if d.isoformat() not in sessions]
    oc = outcomes(rows)
    att = [r for r in rows if r.get("attested_forward")]
    by_h = {}
    for h in HORIZONS:
        m = [o for o in oc if o["h"] == h and o["attested_forward"]]
        by_h[str(h)] = {"matured_attested": len(m),
                        "earliest_maturity": min((r["matures"][str(h)] for r in att), default=None)}
    latest = sessions[-1] if sessions else None
    expected = tc.expected_latest_completed_session().isoformat()
    continuity = "empty" if not sessions else ("gap" if gaps else ("stale" if latest < expected else "ok"))
    return {
        "version": ENGINE_VERSION, "rule_hash": RULE_HASH, "generated_at": datetime.now(timezone.utc).isoformat(),
        "ledger": LEDGER.relative_to(ROOT).as_posix(),
        "first_session": sessions[0] if sessions else None, "latest_session": latest, "expected_session": expected,
        "sessions": len(sessions), "observations": len(rows), "attested_observations": len(att),
        "eligible_observations": sum(1 for r in rows if (r.get("payload") or {}).get("eligible")),
        "continuity": continuity, "gaps": gaps,
        "horizons": by_h,
        "learning_state": "UNPROVEN",
        "notes": ["server-generated from public inputs; independent of browser visits",
                  "gaps are explicit and never backfilled as forward",
                  "horizons are NYSE trading sessions after the observation session"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args(argv)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    existing = read_ledger()
    have = {r["event_id"] for r in existing}
    new, reason = build_observations(data, source_sha=os.getenv("GITHUB_SHA"), run_id=os.getenv("GITHUB_RUN_ID"))
    add = [r for r in new if r["event_id"] not in have]
    old_lines = committed_lines()
    lines = [x for x in (LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else []) if x.strip()]
    lines += [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in add]
    ok, why = check_append_only(old_lines, lines)
    if not ok:
        print(f"::error title=Forward observations::APPEND_ONLY_VIOLATION {why}")
        return 1
    rows = existing + add
    st = status(rows)
    print(f"::notice title=Forward observations::FORWARD_OBS reason={reason} added={len(add)} sessions={st['sessions']} "
          f"continuity={st['continuity']} gaps={len(st['gaps'])} latest={st['latest_session']}")
    if st["continuity"] in ("gap", "stale"):
        print(f"::warning title=Forward observations::FORWARD_OBS_{st['continuity'].upper()} {','.join(st['gaps'][-5:])}")
    if a.check_only:
        return 0
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if add:
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, LEDGER)
    STATUS.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
