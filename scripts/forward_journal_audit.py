#!/usr/bin/env python3
"""Server-side continuity audit of the private forward journal (forward_journal_entries).

Runs in GitHub Actions with the existing service credentials. The repository is public, so the
emitted annotation carries enums only (no counts, symbols, dates, prices or ids):
  continuity : empty | ok | gap | stale
  attestation: PASS (no late upload is marked forward-attested) | FAIL
  provenance : PASS (every row has a server stamp and content hash) | FAIL
A 'gap' is a weekday between the first and latest journal date with no entry at all; it is a data
continuity fact to investigate, never something to backfill as Genuine Forward.
"""
from __future__ import annotations
import json, os, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

MATCH_ENUMS = {"present": {"yes", "no"}, "match": {"all", "partial", "none", "n/a"},
               "first_seen": {"before_publication", "pre_open", "after_open", "unknown", "n/a"}}
ENUMS = {"continuity": {"empty", "ok", "gap", "stale", "not_configured"},
         "attestation": {"PASS", "FAIL", "n/a"}, "provenance": {"PASS", "FAIL", "n/a"}}
STALE_WEEKDAYS = 5


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def weekdays_between(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def summarize(rows, today: date | None = None):
    today = today or datetime.now(timezone.utc).date()
    rows = list(rows or [])
    if not rows:
        return {"continuity": "empty", "attestation": "n/a", "provenance": "n/a"}
    days = sorted({d for d in (_d(r.get("journal_date")) for r in rows) if d})
    attest_bad = any(r.get("forward_attested") and r.get("capture_mode") != "live_sync" for r in rows)
    prov_bad = any(not r.get("server_received_at") or not r.get("content_sha") for r in rows)
    continuity = "ok"
    if days:
        have = set(days)
        if any(d not in have for d in weekdays_between(days[0], days[-1])):
            continuity = "gap"
        if len(list(weekdays_between(days[-1] + timedelta(days=1), today))) > STALE_WEEKDAYS:
            continuity = "stale"
    return {"continuity": continuity, "attestation": "FAIL" if attest_bad else "PASS",
            "provenance": "FAIL" if prov_bad else "PASS"}


def match_sessions(rows, proposals):
    """Per session, compare uploaded browser rows (grade C by default) with the independent
    reconstruction from forward_evidence_audit.jsonl. Enums only; never changes capture_mode."""
    from datetime import datetime as _dt
    by = {}
    for r in rows or []:
        by.setdefault(str(r.get("journal_date"))[:10], []).append(r)
    out = {}
    for p in proposals:
        s = p["session"]
        recon = {o["symbol"]: o for o in ((p.get("reconstruction") or {}).get("observations") or [])}
        mine = by.get(s, [])
        if not mine:
            out[s] = {"present": "no", "match": "n/a", "first_seen": "n/a"}
            continue
        ok = 0
        for r in mine:
            pay = r.get("payload") or {}
            o = recon.get(str(r.get("symbol") or "").upper())
            if o and o["stage"] == pay.get("stage") and o["decision"] == pay.get("decision"):
                ok += 1
        match = "n/a" if not recon else ("all" if ok == len(mine) else "partial" if ok else "none")
        seen = sorted(str(r.get("original_first_seen_at") or "") for r in mine if r.get("original_first_seen_at"))
        ev = p.get("evidence") or {}
        first = "unknown"
        if seen and ev.get("commit_time"):
            t0 = seen[0].replace("Z", "+00:00")
            nopen = str(p.get("next_open") or "").replace("Z", "+00:00")
            if t0 < ev["commit_time"].replace("Z", "+00:00"):
                first = "before_publication"
            elif not nopen or t0 < nopen:
                first = "pre_open"
            else:
                first = "after_open"
        out[s] = {"present": "yes", "match": match, "first_seen": first}
    for v in out.values():
        for k, x in v.items():
            if x not in MATCH_ENUMS[k]:
                raise ValueError("unsanitized match value")
    return out


def assert_sanitized(out):
    for k, v in out.items():
        if k not in ENUMS or v not in ENUMS[k]:
            raise ValueError(f"unsanitized {k}")


def annotation_lines(out):
    assert_sanitized(out)
    lines = ["::notice title=MyAlpha forward journal (enums only)::FORWARD_JOURNAL "
             + json.dumps(out, sort_keys=True, separators=(",", ":"))]
    if out.get("attestation") == "FAIL" or out.get("provenance") == "FAIL":
        lines.append("::warning title=MyAlpha forward journal::FORWARD_JOURNAL_INTEGRITY_FAILING")
    elif out.get("continuity") in ("gap", "stale"):
        lines.append(f"::warning title=MyAlpha forward journal::FORWARD_JOURNAL_{out['continuity'].upper()}")
    return lines


def fetch_rows():
    """Minimal columns, paginated (PostgREST caps a page at 1000 rows)."""
    import urllib.request
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not base or not key:
        return None
    cols = "journal_date,capture_mode,forward_attested,server_received_at,content_sha"
    out, start, page = [], 0, 1000
    while True:
        req = urllib.request.Request(f"{base.rstrip('/')}/rest/v1/forward_journal_entries?select={cols}&order=journal_date.asc",
                                     headers={"apikey": key, "Authorization": f"Bearer {key}", "Range-Unit": "items",
                                              "Range": f"{start}-{start + page - 1}", "User-Agent": "MyAlpha-Forward-Audit"})
        with urllib.request.urlopen(req, timeout=20) as r:
            batch = json.loads(r.read().decode("utf-8"))
        out.extend(batch)
        if len(batch) < page:
            return out
        start += page


def fetch_match_rows():
    import urllib.request
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not base or not key:
        return None
    cols = "journal_date,symbol,payload,original_first_seen_at,capture_mode"
    out, start = [], 0
    while True:
        req = urllib.request.Request(f"{base.rstrip('/')}/rest/v1/forward_journal_entries?select={cols}&order=journal_date.asc",
                                     headers={"apikey": key, "Authorization": f"Bearer {key}", "Range-Unit": "items",
                                              "Range": f"{start}-{start + 999}", "User-Agent": "MyAlpha-Forward-Audit"})
        with urllib.request.urlopen(req, timeout=20) as r:
            batch = json.loads(r.read().decode("utf-8"))
        out.extend(batch)
        if len(batch) < 1000:
            return out
        start += 1000


def main():
    if "--match" in sys.argv:
        path = ROOT / "research" / "archive" / "forward_evidence_audit.jsonl"
        proposals = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        latest = {}
        for p in proposals:
            latest[p["session"]] = p
        res = match_sessions(fetch_match_rows() or [], list(latest.values()))
        for s in sorted(res):
            print(f"::notice title=Forward evidence match::FORWARD_MATCH {s} grade={latest[s].get('proposed_grade')} "
                  + " ".join(f"{k}={v}" for k, v in res[s].items()))
        return 0
    try:
        rows = fetch_rows()
    except Exception:
        rows = None  # table not deployed yet: fail-soft
    out = {"continuity": "not_configured", "attestation": "n/a", "provenance": "n/a"} if rows is None else summarize(rows)
    for line in annotation_lines(out):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
