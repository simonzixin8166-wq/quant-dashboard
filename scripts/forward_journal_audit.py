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


def main():
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
