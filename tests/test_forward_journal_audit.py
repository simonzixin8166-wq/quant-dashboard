"""Forward journal audit: enums only, detects gaps/staleness and attestation violations."""
import importlib.util, json
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fja", ROOT / "scripts" / "forward_journal_audit.py")
fja = importlib.util.module_from_spec(spec); spec.loader.exec_module(fja)

def r(d, mode="live_sync", att=True, sha="abc", stamp="2026-10-09T00:00:00Z", sym="ZZSYM"):
    return {"journal_date": d, "capture_mode": mode, "forward_attested": att, "content_sha": sha,
            "server_received_at": stamp, "symbol": sym, "payload": {"price": 77.5}}

T = date(2026, 10, 9)
assert fja.summarize([], T)["continuity"] == "empty"
ok = [r("2026-10-05"), r("2026-10-06"), r("2026-10-07"), r("2026-10-08"), r("2026-10-09")]
assert fja.summarize(ok, T) == {"continuity": "ok", "attestation": "PASS", "provenance": "PASS"}
# weekend is not a gap; a missing weekday is
assert fja.summarize([r("2026-10-02"), r("2026-10-05")], date(2026, 10, 5))["continuity"] == "ok"
assert fja.summarize([r("2026-10-05"), r("2026-10-07")], T)["continuity"] == "gap"
# stale: nothing for > 5 weekdays
assert fja.summarize([r("2026-09-28")], T)["continuity"] == "stale"
# late upload marked attested → FAIL; missing server stamp → FAIL
assert fja.summarize([r("2026-10-09", mode="late_upload", att=True)], T)["attestation"] == "FAIL"
assert fja.summarize([r("2026-10-09", mode="late_upload", att=False)], T)["attestation"] == "PASS"
assert fja.summarize([r("2026-10-09", sha="")], T)["provenance"] == "FAIL"
# public output: enums only, no private values
text = "\n".join(fja.annotation_lines(fja.summarize(ok + [r("2026-10-08", sym="SECRETSYM")], T)))
for s in ("ZZSYM", "SECRETSYM", "77.5", "2026-10", "abc"):
    assert s not in text, s
pub = json.loads(text.split("FORWARD_JOURNAL ", 1)[1].split("\n")[0])
assert set(pub) == {"continuity", "attestation", "provenance"} and not any(isinstance(v, int) for v in pub.values())
try:
    fja.annotation_lines({"continuity": "ok", "rows": 5}); raise SystemExit("count leaked")
except ValueError:
    pass
# the migration keeps provenance server-side
mig = (ROOT / "supabase/migrations/202610090001_forward_journal_private.sql").read_text()
assert "new.server_received_at := now()" in mig and "FORWARD_JOURNAL_APPEND_ONLY" in mig
assert "revoke update, delete, truncate on public.forward_journal_entries from authenticated" in mig
assert "revoke all on public.forward_journal_entries from anon" in mig
print("PASS forward journal audit / migration contract")
