#!/usr/bin/env python3
"""Record-level diff of the retrieval inputs between two pinned quant-dashboard commits (GPT #133 6620929885 §A1).

Explains, ID by ID, why counts moved between the 11/3 scan (e6f4b897) and the manifest commit (8ae72dfb). Nothing is
hard-coded: every number below comes from `git show <commit>:<path>` of the given repo. Read-only.

  python scripts/retrieval_history_diff.py --repo <quant-dashboard clone with full history> \
      --old e6f4b897c... --new 8ae72dfb30a0... --out research/specs/retrieval/history_diff.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "kr-history-diff-0.1"
# (name, path, list key or None for JSONL, stable id field; "record.id" = nested)
INPUTS = [
    ("source_reading", "docs/research/source_reading_memory.json", "records", "source_id"),
    ("source_store", "research/store/source_store.json", "records", "record.id"),
    ("forward_observations", "research/archive/forward_observations.jsonl", None, "event_id"),
    ("forward_outcomes", "research/archive/forward_outcomes.jsonl", None, "event_id"),
    ("event_outcomes", "research/archive/event_outcomes.jsonl", None, "outcome_id"),
    ("auto_research_journal", "research/knowledge/auto_research_journal.jsonl", None, "record_id"),
    ("market_state_outcomes", "research/archive/market_state_outcomes.jsonl", None, "outcome_id"),
    ("macro_regime_observations", "research/archive/macro_regime_observations.jsonl", None, "observation_id"),
    ("source_outcome_validation", "docs/research/source_outcome_validation.json", "events", "event_id"),
]


def show(repo: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"])


def rows(raw: bytes, key):
    if key is None:
        return [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    d = json.loads(raw.decode("utf-8"))
    return d.get(key, [])


def get_id(r: dict, field: str):
    cur = r
    for part in field.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def canon(r) -> str:
    return json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def diff_one(repo: Path, old: str, new: str, name: str, path: str, key, idf: str) -> dict:
    ro, rn = show(repo, old, path), show(repo, new, path)
    a, b = rows(ro, key), rows(rn, key)
    A = {get_id(r, idf): r for r in a}
    B = {get_id(r, idf): r for r in b}
    added = sorted(str(k) for k in B.keys() - A.keys())
    removed = sorted(str(k) for k in A.keys() - B.keys())
    changed = sorted(str(k) for k in A.keys() & B.keys() if canon(A[k]) != canon(B[k]))
    fields, order_only = {}, {}
    for k in A.keys() & B.keys():
        x, y = A[k], B[k]
        if canon(x) == canon(y) or not isinstance(x, dict):
            continue
        for f in sorted(set(x) | set(y)):
            if canon(x.get(f)) != canon(y.get(f)):
                fields[f] = fields.get(f, 0) + 1
                same_multiset = (isinstance(x.get(f), list) and isinstance(y.get(f), list)
                                 and sorted(map(canon, x[f])) == sorted(map(canon, y[f])))
                order_only[f] = order_only.get(f, 0) + (1 if same_multiset else 0)
    out = {"name": name, "path": path, "id_field": idf,
           "changed_fields": {f: {"records": n, "list_order_only": order_only[f]} for f, n in sorted(fields.items())},
           "old": {"rows": len(a), "unique_ids": len(A), "sha256": hashlib.sha256(ro).hexdigest()},
           "new": {"rows": len(b), "unique_ids": len(B), "sha256": hashlib.sha256(rn).hexdigest()},
           "added": len(added), "removed": len(removed), "changed": len(changed),
           "added_ids": added, "removed_ids": removed, "changed_ids": changed}
    if key is None:  # JSONL: are the old lines a byte-identical prefix of the new file?
        old_lines = ro.decode("utf-8").splitlines(keepends=True)
        new_lines = rn.decode("utf-8").splitlines(keepends=True)
        out["jsonl_old_is_prefix"] = new_lines[:len(old_lines)] == old_lines
    if name == "source_reading":
        pa = {k: len(v.get("propositions") or []) for k, v in A.items()}
        pb = {k: len(v.get("propositions") or []) for k, v in B.items()}
        out["propositions"] = {"old": sum(pa.values()), "new": sum(pb.values()),
                               "in_added_sources": {str(k): pb[k] for k in B.keys() - A.keys()},
                               "count_changed_in_common_sources": sum(1 for k in A.keys() & B.keys() if pa[k] != pb[k])}
    return out


def build(repo: Path, old: str, new: str) -> dict:
    full = lambda c: subprocess.check_output(["git", "-C", str(repo), "rev-parse", c]).decode().strip()
    return {"diff_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "old_commit": full(old), "new_commit": full(new),
            "inputs": [diff_one(repo, full(old), full(new), *x) for x in INPUTS]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    d = build(Path(a.repo).resolve(), a.old, a.new)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for x in d["inputs"]:
        extra = f" prefix={x.get('jsonl_old_is_prefix')}" if "jsonl_old_is_prefix" in x else ""
        print(f"{x['name']}: {x['old']['rows']} -> {x['new']['rows']} added={x['added']} removed={x['removed']} changed={x['changed']}{extra}")
    if "propositions" in d["inputs"][0]:
        print("propositions:", json.dumps(d["inputs"][0]["propositions"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
