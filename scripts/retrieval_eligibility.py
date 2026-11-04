#!/usr/bin/env python3
"""Production-eligibility evaluator + append-only rejection audit (contracts kr-0.3.1 §2.3; GPT #133 6621145320 B2).

Research-only. Every row is evaluated against research/specs/retrieval/eligibility_contract.json; every rejection
appends exactly one JSON line {reason, kind, fields, source_file, source_sha, row_id, audited_at} to the audit file.
The audit file is opened in append mode only: it is never truncated, rewritten or deduplicated. Being listed in the
inventory never makes a row eligible. Today no row carries owner_production_approval_id, so every row is rejected.
Nothing in production reads this module or its output (see tests/test_retrieval_isolation.py).

  python scripts/retrieval_eligibility.py --audit <index build audit .jsonl>   # caller-supplied path; this module names no index path
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "specs" / "retrieval" / "eligibility_contract.json"
ORDER = ["type_never_eligible", "missing_flag", "null_flag", "unknown_value", "flag_conflict", "value_mismatch",
         "no_owner_approval"]
# kind -> (file, list key or None for JSONL, id field)
REAL_SOURCES = {
    "forward_observation": ("research/archive/forward_observations.jsonl", None, "event_id"),
    "forward_observation_promoted": ("research/archive/forward_observations_promoted.jsonl", None, "event_id"),
    "forward_outcome": ("research/archive/forward_outcomes.jsonl", None, "event_id"),
    "rule": ("docs/research/source_rule_lifecycle.json", "rules", "rule_id"),
    "auto_research": ("research/knowledge/auto_research_journal.jsonl", None, "record_id"),
    "shadow_case": ("research/knowledge/shadow_research_cases.jsonl", None, "case_id"),
    "proposition": ("docs/research/source_reading_memory.json", "records", "source_id"),
    "event_outcome": ("research/archive/event_outcomes.jsonl", None, "outcome_id"),
    "fundamental_outcome": ("research/archive/fundamental_outcomes.jsonl", None, "observation_id"),
    "incident": ("research/archive/operational_incidents.jsonl", None, "issue_key"),
}


def load_contract(path: Path = CONTRACT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _conflict(kind: str, row: dict) -> list:
    if kind == "forward_observation" and row.get("market_as_of") != row.get("session"):
        return ["market_as_of", "session"]
    if kind == "forward_outcome":
        if row.get("eligible") is True and row.get("status") != "matured":
            return ["eligible", "status"]
        if row.get("group") != "genuine_forward":
            return ["group"]
    if kind == "rule" and row.get("eligible_for_production") is True and row.get("scoreable_as_method_performance") is False:
        return ["eligible_for_production", "scoreable_as_method_performance"]
    if kind in ("auto_research", "shadow_case") and row.get("production_use") is True and row.get("shadow") is True:
        return ["production_use", "shadow"]
    return []


def evaluate(kind: str, row: dict, contract: dict) -> tuple[bool, str | None, list]:
    """(eligible, reason, fields). First failing check in ORDER wins."""
    k = contract["kinds"].get(kind)
    if not k or not k["approval_capable"]:
        return False, "type_never_eligible", []
    req = k["required"]
    miss = [f for f in req if f not in row]
    if miss:
        return False, "missing_flag", miss
    nul = [f for f in req if row[f] is None]
    if nul:
        return False, "null_flag", nul
    bad = [f for f, want in req.items() if type(row[f]) is not type(want)]
    if bad:
        return False, "unknown_value", bad
    c = _conflict(kind, row)
    if c:
        return False, "flag_conflict", c
    mism = [f for f, want in req.items() if row[f] != want]
    if mism:
        return False, "value_mismatch", mism
    appr = contract["owner_approval_field"]
    if not isinstance(row.get(appr), str) or not row[appr].strip():
        return False, "no_owner_approval", [appr]
    return True, None, []


class AuditLog:
    """Append-only. open('a') only; never truncates; one line per rejection."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, rec: dict) -> None:
        for f in ("reason", "kind", "fields", "source_file", "source_sha"):
            if f not in rec or rec[f] is None:
                raise ValueError(f"audit record missing {f}")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def audit_rows(kind: str, rows, source_file: str, source_sha: str, log: AuditLog, contract: dict, id_field=None) -> dict:
    counts = {"rows": 0, "eligible": 0, "rejected": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        counts["rows"] += 1
        ok, reason, fields = evaluate(kind, r, contract)
        if ok:
            counts["eligible"] += 1
            continue
        counts["rejected"] += 1
        log.append({"reason": reason, "kind": kind, "fields": fields, "source_file": source_file,
                    "source_sha": source_sha, "row_id": r.get(id_field) if id_field else None, "audited_at": now})
    return counts


def load_real(kind: str, root: Path = ROOT):
    path, key, idf = REAL_SOURCES[kind]
    raw = (root / path).read_bytes()
    if key is None:
        rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    else:
        rows = json.loads(raw.decode("utf-8")).get(key, [])
    return rows, path, hashlib.sha256(raw).hexdigest(), idf


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True, help="append-only audit path, supplied by the caller (the module hardcodes no index path)")
    a = ap.parse_args(argv)
    contract, log, total = load_contract(), AuditLog(Path(a.audit)), {}
    for kind in REAL_SOURCES:
        rows, path, sha, idf = load_real(kind)
        total[kind] = audit_rows(kind, rows, path, sha, log, contract, idf)
    print(json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
