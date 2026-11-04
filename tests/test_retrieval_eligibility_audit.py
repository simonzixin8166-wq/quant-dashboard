#!/usr/bin/env python3
"""B2 (GPT #133 6621145320): the rejection audit works on real repo rows and on the frozen fixtures.

Proves: one audit line per rejection with reason/kind/fields/source_file/source_sha; append-only across runs (count
grows exactly, earlier bytes unchanged); every current real row is rejected; inventory presence never implies
eligibility; each reason code (missing / null / unknown / conflict / no_owner_approval / never) is produced."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import retrieval_eligibility as re_  # noqa: E402

C = re_.load_contract()
tmp = Path(tempfile.mkdtemp())
audit = tmp / "build_audit.jsonl"
log = re_.AuditLog(audit)
REQ = {"reason", "kind", "fields", "source_file", "source_sha"}

# 1) real rows from the repo: every one rejected, one audit line each
real = {}
for kind in re_.REAL_SOURCES:
    rows, path, sha, idf = re_.load_real(kind)
    real[kind] = re_.audit_rows(kind, rows, path, sha, log, C, idf)
    assert real[kind]["eligible"] == 0, (kind, real[kind])
    assert real[kind]["rejected"] == real[kind]["rows"] > 0, (kind, real[kind])
lines = audit.read_text(encoding="utf-8").splitlines()
assert len(lines) == sum(v["rejected"] for v in real.values())
recs = [json.loads(x) for x in lines]
assert all(REQ <= set(r) and all(r[f] is not None for f in REQ) for r in recs)
assert all(len(r["source_sha"]) == 64 for r in recs)
by_reason = {}
for r in recs:
    by_reason[(r["kind"], r["reason"])] = by_reason.get((r["kind"], r["reason"]), 0) + 1
print("real-row audit:", {k: v for k, v in real.items()})
print("real-row reasons:", {f"{k}|{r}": n for (k, r), n in sorted(by_reason.items())})

# 2) inventory presence never implies eligibility: every inventory-listed kind above is 0 eligible
inv = json.loads((ROOT / "research/specs/retrieval/inventory_manifest.json").read_text(encoding="utf-8"))
listed = {s["path"] for s in inv["sources"]}
for kind, (path, _, _) in re_.REAL_SOURCES.items():
    if path in listed:
        assert real[kind]["eligible"] == 0

# 3) append-only: a second run appends exactly the same number of lines and leaves the earlier bytes intact
before = audit.read_bytes()
n_before = len(before.splitlines())
for kind in re_.REAL_SOURCES:
    rows, path, sha, idf = re_.load_real(kind)
    re_.audit_rows(kind, rows, path, sha, log, C, idf)
after = audit.read_bytes()
assert after[:len(before)] == before, "earlier audit lines were rewritten"
assert len(after.splitlines()) == 2 * n_before
print(f"append-only: {n_before} -> {len(after.splitlines())} lines; prefix sha256 "
      f"{hashlib.sha256(before).hexdigest()[:16]} == {hashlib.sha256(after[:len(before)]).hexdigest()[:16]}")

# 4) each reason code from the frozen fixtures, through the same audit path
fx = tmp / "fixture_audit.jsonl"
flog = re_.AuditLog(fx)
seen = set()
for c in C["cases"]:
    ok, reason, fields = re_.evaluate(c["kind"], c["row"], C)
    assert (ok, reason) == (c["expected"], c["reason"]), (c["kind"], c["case"], ok, reason)
    if not ok:
        flog.append({"reason": reason, "kind": c["kind"], "fields": fields, "source_file": "eligibility_contract.json#cases",
                     "source_sha": hashlib.sha256((ROOT / "research/specs/retrieval/eligibility_contract.json").read_bytes()).hexdigest(),
                     "row_id": c["case"]})
        seen.add(reason)
assert {"missing_flag", "null_flag", "unknown_value", "flag_conflict", "no_owner_approval", "type_never_eligible",
        "value_mismatch"} <= seen, seen
assert len(fx.read_text(encoding="utf-8").splitlines()) == sum(1 for c in C["cases"] if not c["expected"])

# 5) the writer refuses incomplete records instead of writing a partial line
try:
    flog.append({"reason": "missing_flag", "kind": "rule", "fields": [], "source_file": "x"})
    raise AssertionError("incomplete audit record was accepted")
except ValueError:
    pass
print(f"PASS eligibility audit: {len(recs)} real rejections, 0 eligible; append-only; reasons {sorted(seen)}")
