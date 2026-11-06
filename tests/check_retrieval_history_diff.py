#!/usr/bin/env python3
"""Recompute the record-level history diff (old vs new pinned commit) and compare it field by field with the
committed report (GPT #133 6620929885 §A1-A3). Any difference except generated_at fails. Prints an audit record.

  python tests/check_retrieval_history_diff.py --repo <quant-dashboard clone with full history>
"""
import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import retrieval_history_diff as rhd  # noqa: E402
from check_retrieval_inventory import diff  # noqa: E402

REPORT = ROOT / "research" / "specs" / "retrieval" / "history_diff_e6f4b897_8ae72dfb.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--report", default=str(REPORT))
    a = ap.parse_args(argv)
    raw = Path(a.report).read_bytes()
    committed = json.loads(raw)
    fresh = rhd.build(Path(a.repo).resolve(), committed["old_commit"], committed["new_commit"])
    d = diff(committed, fresh)
    per_input = {x["name"]: ("MATCH" if not [p for p in d if p[0].startswith(f"inputs[{i}]")] else "DIFF")
                 for i, x in enumerate(committed["inputs"])}
    record = {"check": "retrieval-history-diff", "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "command": " ".join([Path(sys.executable).name] + sys.argv),
              "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "script_sha256": fresh["script_sha256"], "python": platform.python_version(),
              "report_sha256": hashlib.sha256(raw).hexdigest(),
              "old_commit": fresh["old_commit"], "new_commit": fresh["new_commit"],
              "per_input": per_input, "differences": len(d), "result": "PASS" if not d else "FAIL",
              "summary": {x["name"]: {"added": x["added"], "removed": x["removed"], "changed": x["changed"]} for x in fresh["inputs"]},
              "propositions": fresh["inputs"][0].get("propositions")}
    print(json.dumps(record, ensure_ascii=False, indent=1))
    for p, x, y in d[:40]:
        print(f"DIFF {p}: report={json.dumps(x, ensure_ascii=False)[:160]} recomputed={json.dumps(y, ensure_ascii=False)[:160]}")
    return 0 if not d else 1


if __name__ == "__main__":
    sys.exit(main())
