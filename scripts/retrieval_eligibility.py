#!/usr/bin/env python3
"""Production-eligibility evaluator + append-only rejection audit (contracts kr-0.3.1 §2.3; GPT #133 6621145320 B2).

Research-only. Every row is evaluated against research/specs/retrieval/eligibility_contract.json; every rejection
appends exactly one JSON line {reason, kind, fields, source_file, source_sha, row_id, audited_at} to the audit file.
The audit file is opened in append mode only: it is never truncated, rewritten or deduplicated. Being listed in the
inventory never makes a row eligible. Today the Owner approval registry holds no retrieval approval, so every row is rejected (a non-empty
approval string alone never qualifies; kr-0.3.2).
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
REGISTRY = ROOT / "research" / "specs" / "retrieval" / "owner_approval_registry.json"
# kr-0.3.2: the reason order lives only in the contract (reason_order); evaluate() runs one check per reason, in that
# order, through CHECKS below, so code and contract cannot drift apart.
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


def load_registry(path: Path = REGISTRY) -> dict:
    """Owner approvals, or an empty registry if the file is absent (fail closed: nothing qualifies)."""
    if not Path(path).exists():
        return {"approvals": []}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def approval_ok(approval_id, kind: str, registry: dict, scope: str) -> bool:
    """An approval qualifies only if it exists, is active, has the right scope and lists this kind.
    A non-empty string by itself never qualifies (GPT #133 6624784358 B2)."""
    if not isinstance(approval_id, str) or not approval_id.strip():
        return False
    for a in (registry or {}).get("approvals", []):
        if a.get("approval_id") == approval_id:
            return a.get("status") == "active" and a.get("scope") == scope and kind in (a.get("kinds") or [])
    return False


def _checks(kind, row, contract, registry):
    k = contract["kinds"].get(kind)
    req = (k or {}).get("required", {})
    appr = contract["owner_approval_field"]
    scope = contract["approval_registry"]["scope"]
    present = lambda: [f for f in req if f in row]
    return {
        "type_never_eligible": lambda: [] if (k and k["approval_capable"]) else ["kind"],
        "missing_flag": lambda: [f for f in req if f not in row],
        "null_flag": lambda: [f for f in present() if row[f] is None],
        "unknown_value": lambda: [f for f in present() if row[f] is not None and type(row[f]) is not type(req[f])],
        "flag_conflict": lambda: _conflict(kind, row),
        "value_mismatch": lambda: [f for f in present() if row[f] != req[f]],
        "no_owner_approval": lambda: [] if approval_ok(row.get(appr), kind, registry, scope) else [appr],
    }


def evaluate(kind: str, row: dict, contract: dict, registry: dict | None = None) -> tuple[bool, str | None, list]:
    """(eligible, reason, fields). Runs the checks in contract['reason_order']; the first failing one wins.
    registry=None loads the real Owner approval registry (today: no retrieval approvals, so nothing is eligible)."""
    registry = load_registry() if registry is None else registry
    checks = _checks(kind, row, contract, registry)
    order = contract["reason_order"]
    assert set(order) == set(checks), f"reason_order and checks differ: {set(order) ^ set(checks)}"
    for reason in order:
        fields = checks[reason]()
        if fields:
            return False, reason, ([] if reason == "type_never_eligible" else fields)
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


def audit_rows(kind: str, rows, source_file: str, source_sha: str, log: AuditLog, contract: dict, id_field=None,
               registry: dict | None = None) -> dict:
    registry = load_registry() if registry is None else registry
    counts = {"rows": 0, "eligible": 0, "rejected": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        counts["rows"] += 1
        ok, reason, fields = evaluate(kind, r, contract, registry)
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
