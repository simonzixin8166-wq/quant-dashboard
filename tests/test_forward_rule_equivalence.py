"""Rule-equivalence evidence entries: append-only, evidence only, never a promotion."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rows = [json.loads(x) for x in (ROOT / "research/archive/forward_evidence_audit.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
eq = [r for r in rows if r.get("kind") == "rule_equivalence_check"]
assert len(eq) >= 7
assert len({r["audit_id"] for r in rows}) == len(rows)                     # ids unique (append-only, idempotent)
for r in eq:
    assert r["review_class"] in ("ready_for_independent_review", "needs_evidence")
    assert r["uncertainties"] and "promoted" not in json.dumps(r) and r["reviewer"] == "claude-tool"
    assert all(len(v or "") == 40 for v in r["rule_file_blobs"].values())  # real blob ids, not commit:path placeholders
    if r["review_class"] == "ready_for_independent_review":
        assert r["equivalent_on_grid"] is True and r["diff_count"] == 0
assert not any(r.get("session") in ("2026-09-28", "2026-10-01") and r.get("kind") == "rule_equivalence_check" for r in rows)
# forensics-1 / forensics-2 entries are preserved unchanged alongside
assert sum(1 for r in rows if r.get("proposal_version") == "forensics-1") == 9
assert sum(1 for r in rows if r.get("proposal_version") == "forensics-2") == 9
print("PASS forward rule equivalence evidence")
