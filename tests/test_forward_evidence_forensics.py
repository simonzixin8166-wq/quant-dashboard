"""Forensics proposals: independent pre-open evidence → A_pending_review; intraday/after-open → B; none → GAP.
Matching browser rows is enums-only and never alters capture_mode."""
import importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ff = load("ff", "forward_evidence_forensics.py"); fja = load("fja2", "forward_journal_audit.py")

def data(session, stage="二次启动", score=80):
    return {"trend_pulse": {"LITE": {"available": True, "date": session, "state": stage, "score": score},
                            "SOFI": {"available": True, "date": session, "state": "趋势恶化", "score": -88}},
            "market_indicators": {"spx": {"day_chg": 0.001}, "ixic": {"day_chg": 0.001}, "vix": {"close": 15}}}
utc = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
commits = [
    ("c1", utc("2026-09-28T16:50:00"), "github-actions", data("2026-09-28", "修复中", 10)),   # intraday
    ("c2", utc("2026-09-29T01:14:00"), "github-actions", data("2026-09-28")),                # post close, pre open
    ("c3", utc("2026-10-02T14:49:00"), "github-actions", data("2026-10-01")),                # after next open
]
runs = {"c2": [{"id": 1, "name": "pages build and deployment", "created_at": "2026-09-29T01:14:22Z"}]}
out = ff.build(["2026-09-28", "2026-09-29", "2026-10-01"], commits, runs_fn=lambda h: runs.get(h, []), now=utc("2026-10-09T05:00:00"))
g = {e["session"]: e for e in out}
assert g["2026-09-28"]["proposed_grade"] == "A_pending_review" and g["2026-09-28"]["evidence"]["commit"] == "c2"
assert g["2026-09-28"]["publication_phases"] == {"intraday": 1, "post_close_pre_open": 1, "after_next_open": 0}
assert g["2026-09-28"]["reconstruction"]["eligible"] == ["LITE"]
assert g["2026-09-28"]["matures"]["20"] == "2026-10-26" and g["2026-09-28"]["status"] == "proposed"
assert g["2026-09-29"]["proposed_grade"] == "none"
assert g["2026-10-01"]["proposed_grade"] == "B"
# pre-open commit without GitHub-side corroboration is only B
out2 = ff.build(["2026-09-28"], commits, runs_fn=lambda h: [], now=utc("2026-10-09T05:00:00"))
assert out2[0]["proposed_grade"] == "B"
# deterministic ids (append-only idempotency)
assert [e["audit_id"] for e in out] == [e["audit_id"] for e in ff.build(["2026-09-28", "2026-09-29", "2026-10-01"], commits, runs_fn=lambda h: runs.get(h, []))]
# browser rows matched → enums only
rows = [{"journal_date": "2026-09-28", "symbol": "LITE", "payload": {"stage": "二次启动", "decision": "修复候选"}, "original_first_seen_at": "2026-09-29T02:00:00Z", "capture_mode": "late_upload"},
        {"journal_date": "2026-10-01", "symbol": "LITE", "payload": {"stage": "修复中", "decision": "修复候选"}, "original_first_seen_at": "2026-10-01T20:00:00Z"}]
m = fja.match_sessions(rows, out)
assert m["2026-09-28"] == {"present": "yes", "match": "all", "first_seen": "pre_open"}, m
assert m["2026-09-29"] == {"present": "no", "match": "n/a", "first_seen": "n/a"}
assert m["2026-10-01"]["first_seen"] == "before_publication"
assert rows[0]["capture_mode"] == "late_upload"   # never changed
assert "LITE" not in json.dumps(m)
print("PASS forward evidence forensics")
