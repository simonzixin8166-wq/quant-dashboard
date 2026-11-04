#!/usr/bin/env python3
"""Executable check of the frozen retrieval contracts kr-0.3.1 (GPT #133 6620929885 §B, §C, §D1).

Uses small reference functions written from the contract text to show the rules are unambiguous. They are NOT the
future index implementation; that one must pass the same fixtures.
  B: every eligibility fixture (legal / missing / null / unknown value / conflict / never-eligible) gives the frozen
     result and the frozen reason code; current-reality rows stay false.
  C: the blind-set canonical form reproduces the committed example hashes, and the hash is order- and CRLF-invariant.
  D1: every inventory source has an admission class; unknown, missing or excluded classes are rejected.
"""
import hashlib
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "research" / "specs" / "retrieval"

# ---------- B: production eligibility ----------
E = json.loads((SPEC / "eligibility_contract.json").read_text(encoding="utf-8"))
APPROVAL = E["owner_approval_field"]


def conflict(kind: str, row: dict) -> bool:
    if kind == "forward_observation":
        return row.get("market_as_of") != row.get("session")
    if kind == "forward_outcome":
        return (row.get("eligible") is True and row.get("status") != "matured") or row.get("group") != "genuine_forward"
    if kind == "rule":
        return row.get("eligible_for_production") is True and row.get("scoreable_as_method_performance") is False
    if kind in ("auto_research", "shadow_case"):
        return row.get("production_use") is True and row.get("shadow") is True
    return False


def eligibility(kind: str, row: dict):
    k = E["kinds"].get(kind)
    if not k or not k["approval_capable"]:
        return False, "type_never_eligible"
    req = k["required"]
    for f in req:
        if f not in row:
            return False, "missing_flag"
    for f in req:
        if row[f] is None:
            return False, "null_flag"
    for f, want in req.items():
        if type(row[f]) is not type(want):
            return False, "unknown_value"
    if conflict(kind, row):
        return False, "flag_conflict"
    for f, want in req.items():
        if row[f] != want:
            return False, "value_mismatch"
    if not isinstance(row.get(APPROVAL), str) or not row[APPROVAL].strip():
        return False, "no_owner_approval"
    return True, None


kinds_with_cases = {c["kind"] for c in E["cases"]}
assert set(E["kinds"]) <= kinds_with_cases, set(E["kinds"]) - kinds_with_cases
for c in E["cases"]:
    got = eligibility(c["kind"], c["row"])
    assert got == (c["expected"], c["reason"]), (c["kind"], c["case"], got)
for kind, k in E["kinds"].items():  # each approval-capable kind has legal, missing and conflict fixtures
    if k["approval_capable"]:
        names = {c["case"] for c in E["cases"] if c["kind"] == kind}
        assert {"legal", "missing"} <= names and any(n.startswith("conflict") for n in names), (kind, names)
print(f"PASS eligibility contract: {len(E['cases'])} fixtures over {len(E['kinds'])} kinds, fail-closed reasons as frozen")

# ---------- C: blind-set canonical hashing ----------
H = json.loads((SPEC / "blind_hash_spec.json").read_text(encoding="utf-8"))


def norm(x):
    if isinstance(x, str):
        return unicodedata.normalize("NFC", x.replace("\r\n", "\n").replace("\r", "\n"))
    if isinstance(x, list):
        return [norm(i) for i in x]
    if isinstance(x, dict):
        return {norm(k): norm(v) for k, v in x.items()}
    return x


def canon_hash(items) -> str:
    items = sorted((norm(i) for i in items), key=lambda d: d["question_id"])
    return hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


assert canon_hash(H["example_questions"]) == H["example_questions_sha256"]
assert canon_hash(H["example_answers"]) == H["example_answers_sha256"]
shuffled = list(reversed(H["example_questions"]))
crlf = [{**q, "text": q["text"].replace("\n", "\r\n")} for q in H["example_questions"]]
decomposed = [{**q, "text": unicodedata.normalize("NFD", q["text"])} for q in H["example_questions"]]
assert canon_hash(shuffled) == canon_hash(crlf) == canon_hash(decomposed) == H["example_questions_sha256"]
assert canon_hash([{**H["example_questions"][0], "text": H["example_questions"][0]["text"] + " "}] + H["example_questions"][1:]) != H["example_questions_sha256"]
q_ids = {q["question_id"] for q in H["example_questions"]}
a_ids = {a["question_id"] for a in H["example_answers"]}
assert q_ids == a_ids and not any("expect" in q for q in H["example_questions"]), "questions must not carry answer fields"
print("PASS blind-set hash contract: example hashes reproduce; order / CRLF / NFC invariant; whitespace sensitive")

# ---------- D1: source admission ----------
A = json.loads((SPEC / "source_admission.json").read_text(encoding="utf-8"))
ADMIT = {"public", "research-safe"}


def admitted(source: str) -> bool:
    return A["sources"].get(source) in ADMIT


inv = json.loads((SPEC / "inventory_manifest.json").read_text(encoding="utf-8"))
names = [s["name"] for s in inv["sources"]] + [Path(d["path"]).name.replace("history", "data_history") if d["path"] == "data/history" else Path(d["path"]).name for d in inv["directories"]]
missing = [n for n in names if n not in A["sources"]]
assert not missing, f"inventory sources without an admission class: {missing}"
assert all(A["sources"][n] in A["classes"] for n in A["sources"]), "unknown admission class"
assert not admitted("myalpha-ledger-private") and not admitted("supabase") and not admitted("browser_journal")
assert not admitted("some_new_source_not_listed")  # unknown -> reject
print(f"PASS source admission: {len(names)} inventory sources classified; unknown/missing/excluded rejected")
