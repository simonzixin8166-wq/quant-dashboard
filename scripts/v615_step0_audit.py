#!/usr/bin/env python3
"""V6.15 Step 0 read-only audit.

This script intentionally does not modify source or production artifacts.
It reports:
1) published_at semantics by source type,
2) display/evaluation truncation,
3) records.operations vs operation_cases.operations consistency.

It may write only to research/audit when --write is supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "data" / "source_intelligence.json"
OUT = ROOT / "research" / "audit" / "v615_step0_audit.json"


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def timestamp_semantics(record: dict) -> str:
    source = str(record.get("source") or "").lower()
    kind = str(record.get("source_kind") or "").lower()
    if source == "wenxuecity" and kind == "blog":
        # seed_brightline() maps archive article["date"] directly to published_at.
        return "source_archive_publication_date"
    return "upstream_published_at_unverified"


def audit(source: dict) -> dict:
    records = source.get("records") or []
    operation_cases = source.get("operation_cases") or []
    total = int((source.get("counts") or {}).get("records") or len(records))

    ts = defaultdict(lambda: Counter())
    for row in records:
        key = f"{row.get('source') or 'unknown'}|{row.get('source_kind') or 'unknown'}"
        ts[key]["records"] += 1
        if row.get("published_at"):
            ts[key]["published_present"] += 1
        else:
            ts[key]["published_missing"] += 1
        ts[key][timestamp_semantics(row)] += 1

    by_id = {str(r.get("id")): r for r in records if r.get("id") is not None}
    matched = mismatched = missing_from_records = 0
    mismatch_examples = []
    for case in operation_cases:
        rid = str(case.get("id"))
        row = by_id.get(rid)
        if row is None:
            missing_from_records += 1
            if len(mismatch_examples) < 5:
                mismatch_examples.append({"id": rid, "status": "operation_case_outside_records_window"})
            continue
        if digest(row.get("operations") or []) != digest(case.get("operations") or []):
            mismatched += 1
            if len(mismatch_examples) < 5:
                mismatch_examples.append({
                    "id": rid,
                    "status": "operations_hash_mismatch",
                    "records_hash": digest(row.get("operations") or []),
                    "operation_cases_hash": digest(case.get("operations") or []),
                })
        else:
            matched += 1

    actionable_record_ids = {
        str(r.get("id")) for r in records
        if (r.get("operations") or r.get("actions")) and r.get("id") is not None
    }
    case_ids = {str(r.get("id")) for r in operation_cases if r.get("id") is not None}

    return {
        "step": "V6.15 Step 0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "source_intelligence_version": source.get("version"),
        "parser_version": source.get("parser_version"),
        "published_at": {
            "by_source_kind": {k: dict(v) for k, v in sorted(ts.items())},
            "finding": (
                "BrightLine/Wenxuecity blog records map archive article.date to published_at. "
                "For upstream feed records, the current pipeline preserves published_at but "
                "does not separately retain fetched_at, so semantics must be treated as unverified "
                "until a source-specific guarantee exists."
            ),
            "policy": (
                "Verified source publication timestamps may anchor evaluation. "
                "Unverified/missing timestamps must use first_fetched_at conservatively once "
                "persistent source storage is available, or remain excluded from scoreable evidence."
            ),
        },
        "truncation": {
            "normalized_total_records": total,
            "source_intelligence_records_exposed": len(records),
            "source_intelligence_records_limit": 800,
            "source_reading_records_limit": 800,
            "operation_cases_limit": 120,
            "is_source_records_truncated": total > len(records),
            "finding": (
                "source_intelligence_engine writes records=rows[:800]; source_reading_memory "
                "again writes memories[:800]. The 800-record value is therefore a display/storage "
                "window, not the full normalized source population."
            ),
        },
        "operation_consistency": {
            "operation_cases": len(operation_cases),
            "matched_content_hash": matched,
            "mismatched_content_hash": mismatched,
            "operation_cases_outside_records_window": missing_from_records,
            "actionable_records_without_operation_case": len(actionable_record_ids - case_ids),
            "examples": mismatch_examples,
            "finding": (
                "records and operation_cases are derived from the same normalized rows in one build, "
                "but are independently truncated and there is no runtime content-hash assertion. "
                "V6.15.1 must add an explicit consistency guard."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write research/audit output")
    args = parser.parse_args()
    result = audit(load(SOURCE, {}))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
