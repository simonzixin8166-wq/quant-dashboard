#!/usr/bin/env python3
"""Read-only inventory for the unified retrieval design (kr-0.2.1, #133 6620532060 / GPT 6620593762 item 3).

Counts every source the future index would read, at fixed commits of both repos, and reconciles them so a third
party can recompute the numbers. Writes nothing except the manifest given by --out. No network, no production
effect, no private data (the private ledger repo and Supabase are excluded by Owner decision 6594477482).

  python scripts/retrieval_inventory.py --qd . --wx ../wxc-bot --out research/specs/retrieval/inventory_manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = "kr-inventory-0.2.1"
TIME_FIELDS = ["published_at", "first_seen", "first_fetched_at", "captured_at", "generated_at", "session",
               "market_as_of", "as_of", "filing_date", "filed", "scored_at", "matures_on", "created_at",
               "event_at", "observed_at", "discovered_at"]
ID_FIELDS = ["event_id", "record_id", "source_id", "id", "case_id", "observation_id", "outcome_id"]
# (name, repo, path, list key; None = JSONL rows)
SOURCES = [
    ("wx_feed", "wx", "state/research_feed.json", "records"),
    ("source_store", "qd", "research/store/source_store.json", "records"),
    ("source_reading", "qd", "docs/research/source_reading_memory.json", "records"),
    ("rule_lifecycle", "qd", "docs/research/source_rule_lifecycle.json", "rules"),
    ("forward_observations", "qd", "research/archive/forward_observations.jsonl", None),
    ("forward_observations_promoted", "qd", "research/archive/forward_observations_promoted.jsonl", None),
    ("forward_outcomes", "qd", "research/archive/forward_outcomes.jsonl", None),
    ("auto_research_journal", "qd", "research/knowledge/auto_research_journal.jsonl", None),
    ("shadow_research_cases", "qd", "research/knowledge/shadow_research_cases.jsonl", None),
    ("fundamental_observations", "qd", "research/archive/fundamental_observations.jsonl", None),
    ("fundamental_outcomes", "qd", "research/archive/fundamental_outcomes.jsonl", None),
    ("event_outcomes", "qd", "research/archive/event_outcomes.jsonl", None),
    ("market_state_outcomes", "qd", "research/archive/market_state_outcomes.jsonl", None),
    ("macro_regime_observations", "qd", "research/archive/macro_regime_observations.jsonl", None),
    ("operational_incidents", "qd", "research/archive/operational_incidents.jsonl", None),
    ("source_outcome_validation", "qd", "docs/research/source_outcome_validation.json", "events"),
    ("contradictions", "qd", "research/history/contradictions.json", "records"),
    ("method_memory", "qd", "docs/research/method_memory.json", "methods"),
    ("situation_memory", "qd", "docs/research/learning_engine.json", "situation_memory"),
    ("historical_journal", "qd", "docs/research/historical_journal.json", "recent_events"),
]
DIRS = ["research/archive/sec_filings", "research/archive/thesis_revisions",
        "research/archive/options_opportunity_observations", "data/history"]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"]).decode().strip()


def rows(raw: bytes, path: str, key):
    if path.endswith(".jsonl"):
        return [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    d = json.loads(raw.decode("utf-8"))
    x = d.get(key, []) if isinstance(d, dict) else d
    return x if isinstance(x, list) else list(x.values()) if isinstance(x, dict) else []


def flat(r: dict) -> dict:
    out = dict(r)
    if isinstance(r.get("record"), dict):
        for k, v in r["record"].items():
            out.setdefault(k, v)
    return out


def describe(name, repo_tag, root: Path, path: str, key):
    p = root / path
    if not p.exists():
        return {"name": name, "repo": repo_tag, "path": path, "status": "MISSING"}, []
    raw = p.read_bytes()
    rs = [flat(r) for r in rows(raw, path, key) if isinstance(r, dict)]
    n = len(rs)
    idk = next((k for k in ID_FIELDS if n and sum(1 for r in rs if r.get(k)) >= 0.9 * n), None)
    ids = [json.dumps(r.get(idk), sort_keys=True) for r in rs] if idk else []
    dup = sum(c - 1 for c in Counter(ids).values() if c > 1)
    cov = {k: round(sum(1 for r in rs if r.get(k) not in (None, "")) / n, 4)
           for k in TIME_FIELDS if n and any(r.get(k) not in (None, "") for r in rs)}
    return ({"name": name, "repo": repo_tag, "path": path, "file_sha256": sha256(raw), "records": n,
             "id_field": idk, "unique_ids": len(set(ids)) if idk else None, "duplicate_id_rows": dup if idk else None,
             "time_field_coverage": cov, "replayable": bool(cov) and idk is not None}, rs)


def build(qd: Path, wx: Path) -> dict:
    roots = {"qd": qd, "wx": wx}
    out, data = [], {}
    for name, tag, path, key in SOURCES:
        meta, rs = describe(name, tag, roots[tag], path, key)
        out.append(meta)
        data[name] = rs
    dirs = []
    for d in DIRS:
        p = qd / d
        files = sorted(x for x in p.rglob("*") if x.is_file()) if p.exists() else []
        dirs.append({"path": d, "files": len(files),
                     "files_sha256": {str(f.relative_to(qd)): sha256(f.read_bytes()) for f in files}})
    # reconciliation and linkage
    fid = {r["id"] for r in data["wx_feed"]}
    sid = {r.get("id") for r in data["source_store"]}
    rid = {r.get("source_id") for r in data["source_reading"]}
    obs = {r["event_id"] for r in data["forward_observations"]} | {r["event_id"] for r in data["forward_observations_promoted"]}
    outc = data["forward_outcomes"]
    only_store, only_feed = sorted(sid - fid), sorted(fid - sid)
    recon = {
        "feed_vs_store": {"feed": len(fid), "store": len(sid), "only_in_store": len(only_store), "only_in_feed": len(only_feed),
                          "identity": f"{len(sid)} = {len(fid)} - {len(only_feed)} + {len(only_store)}",
                          "holds": len(sid) == len(fid) - len(only_feed) + len(only_store),
                          "only_in_store_by_kind": dict(Counter(f"{(r.get('source_kind'))}|{r.get('author')}|{r.get('ingest_type')}"
                                                                for r in data["source_store"] if r.get("id") in set(only_store))),
                          "only_in_store_ids": only_store, "only_in_feed_ids": only_feed},
        "store_vs_reading": {"reading_orphans": sorted(rid - sid), "store_without_reading": len(sid - rid),
                             "propositions": sum(len(r.get("propositions") or []) for r in data["source_reading"])},
        "outcomes_vs_observations": {"outcomes": len(outc), "orphan_outcomes": sum(1 for o in outc if o.get("event_id") not in obs),
                                     "by_group_h_status": dict(Counter(f"{o.get('group')}|h{o.get('h')}|{o.get('status')}" for o in outc)),
                                     "genuine_forward_outcomes": sum(1 for o in outc if o.get("group") == "genuine_forward")},
        "fundamental_one_to_many": {"observations": len(data["fundamental_observations"]),
                                    "outcomes": len(data["fundamental_outcomes"]),
                                    "distinct_observation_ids_in_outcomes": len({o.get("observation_id") for o in data["fundamental_outcomes"]})},
        "store_timestamp_confidence": dict(Counter(str(r.get("timestamp_confidence")) for r in data["source_store"])),
        "store_ingest_type": dict(Counter(str(r.get("ingest_type")) for r in data["source_store"])),
    }
    return {"manifest_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script_sha256": sha256(Path(__file__).read_bytes()),
            "commits": {"quant-dashboard": head(qd), "wxc-bot": head(wx)},
            "excluded": ["myalpha-ledger-private (Owner 6594477482)", "Supabase tables", "browser localStorage journal"],
            "sources": out, "directories": dirs, "reconciliation": recon}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qd", default=".")
    ap.add_argument("--wx", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    m = build(Path(a.qd).resolve(), Path(a.wx).resolve())
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    r = m["reconciliation"]
    print(f"inventory {m['commits']} feed/store {r['feed_vs_store']['identity']} holds={r['feed_vs_store']['holds']} "
          f"orphan_outcomes={r['outcomes_vs_observations']['orphan_outcomes']} out_sha256={sha256(Path(a.out).read_bytes())}")
    return 0 if r["feed_vs_store"]["holds"] else 1


if __name__ == "__main__":
    sys.exit(main())
