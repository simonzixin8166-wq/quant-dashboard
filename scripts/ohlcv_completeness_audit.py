#!/usr/bin/env python3
"""P0-2 (#133 6183848571) — per-symbol OHLCV completeness evidence for given NYSE sessions. Read-only.

One row per (symbol, session) of the canonical archive data/history/stooq_watchlist.zip:
  OHLCV values, full-field validity (H ≥ max(O,C), L ≤ min(O,C), all > 0, volume > 0), status present/missing,
  display pool (docs/data.json stocks/core/index), source of the latest append (docs/research/historical_journal.json),
  quarantined conflicts for that date, and — when git history is available — the first commit/time the bar appeared
  in the archive (first_seen), so a bar filled a day late is never presented as known at the time.
Three scopes are kept apart and never substituted for each other:
  archive (canonical history)  ·  homepage (docs/data.json)  ·  event inputs (macro event records).
Usage: python scripts/ohlcv_completeness_audit.py 2026-10-13 2026-10-14
"""
from __future__ import annotations
import io, json, subprocess, sys, zipfile
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "data/history/stooq_watchlist.zip"
JOURNAL = ROOT / "docs" / "research" / "historical_journal.json"
DATA = ROOT / "docs" / "data.json"
OUT_DIR = ROOT / "research" / "audit" / "ohlcv_completeness"


def _rows(zbytes):
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    out = {}
    for n in z.namelist():
        if not n.endswith(".csv"):
            continue
        sym = n.split("/")[-1].replace("_us_d.csv", "").upper()
        lines = z.read(n).decode().strip().splitlines()
        hdr = [h.strip().lower() for h in lines[0].split(",")]
        out[sym] = {l.split(",")[0]: dict(zip(hdr, l.split(","))) for l in lines[-15:]}
    return out


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def first_seen(sessions):
    """{(sym, session): (commit, committed_at)} from the archive's git history; {} when history is unavailable."""
    try:
        log = _git("log", "--format=%H %cI", "--since=2026-10-01", "--", ARCHIVE).decode().split("\n")
    except Exception:
        return {}
    seen = {}
    for line in reversed([l for l in log if l.strip()]):
        h, t = line.split(" ", 1)
        try:
            rows = _rows(_git("show", f"{h}:{ARCHIVE}"))
        except Exception:
            continue
        for sym, by_date in rows.items():
            for s in sessions:
                if s in by_date and (sym, s) not in seen:
                    seen[(sym, s)] = (h[:7], t)
    return seen


INDEX_NO_VOLUME = {"VIX"}  # an index has no traded volume; volume 0 is expected, not a defect


def valid(r, sym=None):
    try:
        o, h, l, c, v = (float(r[k]) for k in ("open", "high", "low", "close", "volume"))
    except Exception:
        return False, "non_numeric_or_missing_field"
    if min(o, h, l, c) <= 0:
        return False, "non_positive_price"
    if h < max(o, c) or l > min(o, c):
        return False, "high_low_inconsistent"
    if v <= 0 and sym not in INDEX_NO_VOLUME:
        return False, "zero_volume"
    return True, None


def captured_before_close(session, first_seen_at):
    """True when the bar entered the archive before 16:15 ET of its own session (an unfinished, intraday bar)."""
    if not first_seen_at:
        return None
    close = datetime.combine(date.fromisoformat(session), time(16, 15), ZoneInfo("America/New_York"))
    return datetime.fromisoformat(first_seen_at) < close


def build(sessions):
    rows = _rows((ROOT / ARCHIVE).read_bytes())
    journal = json.loads(JOURNAL.read_text(encoding="utf-8")) if JOURNAL.exists() else {}
    upd = journal.get("update") or {}
    data = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    display = {s for g in ("stocks", "core", "index") for s in (data.get(g) or {})}
    quarantined = {(q["symbol"], q.get("date")): q for q in upd.get("quarantined") or [] if isinstance(q, dict)}
    fs = first_seen(sessions)
    table = []
    for sym in sorted(rows):
        for s in sessions:
            r = rows[sym].get(s)
            ok, why = valid(r, sym) if r else (False, "missing")
            q = quarantined.get((sym, s))
            table.append({
                "symbol": sym, "session": s, "status": "present" if r else "missing",
                "ohlcv": None if not r else {k: float(r[k]) for k in ("open", "high", "low", "close", "volume") if r.get(k) not in (None, "")},
                "full_fields_valid": ok, "invalid_reason": why,
                "display_pool": sym in display,
                "latest_append_source": (upd.get("sources") or {}).get(sym),
                "first_seen_commit": (fs.get((sym, s)) or (None, None))[0],
                "first_seen_at": (fs.get((sym, s)) or (None, None))[1],
                "captured_before_close": captured_before_close(s, (fs.get((sym, s)) or (None, None))[1]),
                "quarantined_conflict": None if not q else {k: q.get(k) for k in ("old", "new", "source", "reason")},
            })
    summary = {s: {"present": sum(1 for t in table if t["session"] == s and t["status"] == "present"),
                   "valid": sum(1 for t in table if t["session"] == s and t["full_fields_valid"]),
                   "universe": len(rows), "quarantined_conflicts": sum(1 for t in table if t["session"] == s and t["quarantined_conflict"]),
                   "captured_before_close": [t["symbol"] for t in table if t["session"] == s and t["captured_before_close"]]}
               for s in sessions}
    return {"version": 1, "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "scope": "canonical archive data/history/stooq_watchlist.zip (not homepage, not event inputs)",
            "sessions": sessions, "summary": summary, "journal_expected_session": upd.get("expected_session"),
            "fallback_diagnostics_latest": upd.get("fallback_diagnostics") or "not_recorded (instrumented from #133 6183848571 onward)",
            "first_seen_basis": "git history of the archive" if fs else "unavailable (no git history in this checkout)",
            "rows": table}


def main():
    sessions = sys.argv[1:] or [json.loads(JOURNAL.read_text(encoding="utf-8"))["update"]["expected_session"]]
    out = build(sessions)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"{'_'.join(sessions)}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["summary"]), p.relative_to(ROOT))


if __name__ == "__main__":
    main()
