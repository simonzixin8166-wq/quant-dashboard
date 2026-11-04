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
FX_REG = json.loads((ROOT / "tests/fixtures/retrieval/approval_registry_fixture.json").read_text(encoding="utf-8"))
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
    ok, reason, fields = re_.evaluate(c["kind"], c["row"], C, FX_REG)
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
# 6) kr-0.3.2 (GPT 6624784358 B2): a non-empty approval string is not an approval. Forged / unknown / revoked /
# wrong-scope / wrong-kind ids are all rejected (fixtures above); with the REAL registry (no retrieval approval today)
# even the fully legal fixture rows are rejected, so the real state stays 0 eligible.
REAL_REG = re_.load_registry()
assert not [a for a in REAL_REG["approvals"] if a.get("scope") == C["approval_registry"]["scope"]], "unexpected retrieval approval"
for c in C["cases"]:
    if c["expected"]:
        assert re_.evaluate(c["kind"], c["row"], C, REAL_REG) == (False, "no_owner_approval", [C["owner_approval_field"]]), c["kind"]
        assert re_.evaluate(c["kind"], c["row"], C, FX_REG)[0] is True
assert re_.evaluate("rule", {}, C, {"approvals": []})[1] == "missing_flag"
assert re_.load_registry(tmp / "absent.json") == {"approvals": []}  # missing registry -> nothing qualifies
bad_cases = {c["case"] for c in C["cases"] if c["case"].startswith("approval_")}
assert bad_cases == {"approval_forged", "approval_unknown", "approval_revoked", "approval_scope_mismatch", "approval_kind_mismatch"}, bad_cases
# reason order has one source: the contract. Dropping or adding a reason makes evaluate() refuse to run.
broken = dict(C, reason_order=C["reason_order"][:-1])
try:
    re_.evaluate("rule", {}, broken, FX_REG)
    raise AssertionError("evaluate ran with a reason_order that does not match its checks")
except AssertionError as e:
    assert "reason_order and checks differ" in str(e), e
# swapping two reasons in the contract changes the result, i.e. the code follows the contract order
row = {"eligible_for_production": None}
swapped = dict(C, reason_order=["type_never_eligible", "null_flag", "missing_flag", "unknown_value", "flag_conflict", "value_mismatch", "no_owner_approval"])
assert re_.evaluate("rule", row, C, FX_REG)[1] == "missing_flag" and re_.evaluate("rule", row, swapped, FX_REG)[1] == "null_flag"
print("PASS approval registry: forged/unknown/revoked/scope/kind rejected; real registry -> 0 eligible; reason order from contract")
print(f"PASS eligibility audit: {len(recs)} real rejections, 0 eligible; append-only; reasons {sorted(seen)}")
