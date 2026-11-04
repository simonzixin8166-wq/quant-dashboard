#!/usr/bin/env python3
"""Recompute the retrieval inventory at the pinned commits and compare it field by field with the committed manifest.

GPT #133 6620702390 §A.4-5: any difference except the declared non-deterministic field fails. Prints an audit record
(commits, script sha256, manifest sha256, Python version, run time, per-field result) so the log is the evidence.

  python tests/check_retrieval_inventory.py --qd <checkout at pinned qd commit> --wx <checkout at pinned wx commit>
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
import retrieval_inventory as ri  # noqa: E402

MANIFEST = ROOT / "research" / "specs" / "retrieval" / "inventory_manifest.json"
NONDETERMINISTIC = {"generated_at"}


def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if p in NONDETERMINISTIC:
                continue
            if k not in a or k not in b:
                out.append((p, a.get(k, "<missing>"), b.get(k, "<missing>")))
            else:
                out += diff(a[k], b[k], p)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [(f"{path}[len]", len(a), len(b))]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [(path, a, b)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qd", required=True)
    ap.add_argument("--wx", required=True)
    ap.add_argument("--manifest", default=str(MANIFEST))
    a = ap.parse_args(argv)
    committed_raw = Path(a.manifest).read_bytes()
    committed = json.loads(committed_raw)
    fresh = ri.build(Path(a.qd).resolve(), Path(a.wx).resolve())
    # the script that recomputes is the one in this checkout; the manifest must name the same script
    d = diff(committed, fresh)
    top = sorted(set(committed) - NONDETERMINISTIC)
    per_field = {k: ("MATCH" if not [x for x in d if x[0] == k or x[0].startswith(k + ".") or x[0].startswith(k + "[")] else "DIFF")
                 for k in top}
    record = {"check": "retrieval-inventory", "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "command": " ".join([Path(sys.executable).name] + sys.argv),
              "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "python": platform.python_version(), "manifest_sha256": hashlib.sha256(committed_raw).hexdigest(),
              "script_sha256": fresh["script_sha256"], "commits_recomputed": fresh["commits"],
              "commits_in_manifest": committed.get("commits"), "ignored_fields": sorted(NONDETERMINISTIC),
              "per_top_level_field": per_field, "differences": len(d), "result": "PASS" if not d else "FAIL"}
    print(json.dumps(record, ensure_ascii=False, indent=1))
    for p, x, y in d[:40]:
        print(f"DIFF {p}: manifest={json.dumps(x, ensure_ascii=False)[:160]} recomputed={json.dumps(y, ensure_ascii=False)[:160]}")
    return 0 if not d else 1


if __name__ == "__main__":
    sys.exit(main())
