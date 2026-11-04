#!/usr/bin/env python3
"""Weekly forward attribution report (genuine forward, h=20, fea-0.2 + rfi-0.1). Owner-approved 11/3.

Runs inside Learning Quality Weekly so the "outcome -> attribution" step of the learning loop no longer needs a
Claude session. Cohort = every ledger session whose h=20 outcomes are all final (matured / unavailable / invalid).

Every run appends one line to research/reports/attribution/runs.jsonl (status GENERATED / UNCHANGED / NOT RUN / CHECK,
run time, input hashes), so "nothing changed" is never confused with "did not run". Writes, only when the content changed:
  docs/research/forward_attribution_weekly.json   summary (denominators, misses by primary cause, coverage)
  research/reports/attribution/forward_h20_latest.md   full row-by-row report

Explains outcomes, never re-scores them. No rule, threshold, scorecard or production change.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_cohort_report as fcr  # noqa: E402

OUT_JSON = ROOT / "docs" / "research" / "forward_attribution_weekly.json"
OUT_MD = ROOT / "research" / "reports" / "attribution" / "forward_h20_latest.md"
RUNS = ROOT / "research" / "reports" / "attribution" / "runs.jsonl"   # append-only, one line per weekly run
INPUTS = ("forward_observations.jsonl", "forward_outcomes.jsonl")


def build(root: Path = ROOT, now: datetime | None = None) -> tuple[dict, str]:
    lines, issues, summary = fcr.run(root, "genuine_forward", None, 20, stamp=False)
    if not summary["rows"]:
        summary["engineering_acceptance"] = "NOT RUN"
        summary["note_zh"] = "还没有整批到期的交易日（首批 2026-10-08 的 20 日结果在 2026-11-05 收盘后到期）。"
    else:
        summary["note_zh"] = ("归因只解释已到期结果，不改变命中/未命中；每个判断类别在独立样本 ≥20 且入场周数 ≥4 之前，"
                              "只报告数量，不下有效性结论。")
    md = "\n".join(lines) + "\n"
    summary["content_sha"] = hashlib.sha256((json.dumps(summary, sort_keys=True, ensure_ascii=False) + md).encode()).hexdigest()[:16]
    summary["generated_at"] = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return summary, md


def write_if_changed(summary: dict, md: str, out_json: Path = OUT_JSON, out_md: Path = OUT_MD) -> bool:
    try:
        old = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    if old.get("content_sha") == summary["content_sha"] and out_md.exists():
        return False
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(md, encoding="utf-8")
    return True


def run_status(summary: dict, changed: bool) -> str:
    """GPT #133 6594346990 §4: tell 'nothing changed' apart from 'did not run' and from a failed check."""
    acc = summary.get("engineering_acceptance")
    if acc in ("NOT RUN", "CHECK"):
        return acc
    return "GENERATED" if changed else "UNCHANGED"


def run_record(summary: dict, changed: bool, root: Path = ROOT, now: datetime | None = None) -> dict:
    arch = root / "research" / "archive"
    return {"run_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
            "status": run_status(summary, changed),
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "content_sha": summary.get("content_sha"),
            "sessions": [summary["sessions"][0], summary["sessions"][-1]] if summary.get("sessions") else [],
            "rows": summary.get("rows"), "misses": summary.get("misses"),
            "issues": summary.get("issues") or [],
            "inputs_sha256_16": {n: hashlib.sha256((arch / n).read_bytes()).hexdigest()[:16] if (arch / n).exists() else None
                                 for n in INPUTS},
            "attribution_version": summary.get("attribution_version"), "contract_hash": summary.get("contract_hash")}


def append_run(rec: dict, runs: Path = RUNS) -> None:
    runs.parent.mkdir(parents=True, exist_ok=True)
    with runs.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    summary, md = build()
    changed = write_if_changed(summary, md)
    rec = run_record(summary, changed)
    append_run(rec)
    print(f"::notice title=Forward attribution run::status={rec['status']} inputs={rec['inputs_sha256_16']}")
    print(f"::notice title=Forward attribution::{json.dumps({k: summary[k] for k in ('engineering_acceptance', 'rows', 'misses', 'unattributed_R0', 'attribution_coverage')}, ensure_ascii=False)} changed={changed}")
    if summary["engineering_acceptance"] == "CHECK":
        print(f"::warning title=Forward attribution::{'; '.join(summary['issues'])}")
    return 0  # report-only: an acceptance CHECK is surfaced as a warning, never blocks the weekly job


if __name__ == "__main__":
    sys.exit(main())
