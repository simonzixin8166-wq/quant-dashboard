#!/usr/bin/env python3
"""Verify every Owner approval in research/specs/retrieval/owner_approval_registry.json against GitHub (kr-0.3.2,
GPT #133 6624784358 B2/D4).

For each approval: the schema is exact, the scope is known, and its evidence comment exists on the named issue of
this repository, was written by the repository OWNER (author_association == "OWNER") and contains the entry's
`must_contain` marker. Any failure — including a network or permission error — exits 1. Read-only: one GET per
approval with the workflow's read-only GITHUB_TOKEN; nothing is written.

  python scripts/verify_owner_approvals.py            # needs GITHUB_TOKEN and GITHUB_REPOSITORY
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "research" / "specs" / "retrieval" / "owner_approval_registry.json"
COMMON = {"approval_id", "scope", "status", "granted_at", "evidence", "decision"}
SCOPE_KEYS = {"retrieval_production_eligibility": COMMON | {"kinds"},
              "privacy_allowlist": COMMON | {"categories", "value_sha256"}}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def schema_errors(reg: dict) -> list:
    errs, seen = [], set()
    if set(reg.get("scopes", [])) != set(SCOPE_KEYS):
        errs.append("registry scopes differ from the known scopes")
    for a in reg.get("approvals", []):
        aid = a.get("approval_id")
        if not isinstance(aid, str) or not aid or aid in seen:
            errs.append(f"bad or duplicate approval_id {aid!r}")
        seen.add(aid)
        want = SCOPE_KEYS.get(a.get("scope"))
        if want is None:
            errs.append(f"{aid}: unknown scope {a.get('scope')!r}")
            continue
        if set(a) != want:
            errs.append(f"{aid}: keys {sorted(set(a) ^ want)} differ from the {a['scope']} schema")
        if a.get("status") not in ("active", "revoked"):
            errs.append(f"{aid}: status must be active or revoked")
        ev = a.get("evidence") or {}
        if set(ev) != {"issue", "comment_id", "must_contain"} or not all(isinstance(ev.get(k), int) and ev[k] > 0 for k in ("issue", "comment_id")) \
                or not isinstance(ev.get("must_contain"), str) or len(ev["must_contain"]) < 8:
            errs.append(f"{aid}: evidence must be {{issue>0, comment_id>0, must_contain (>=8 chars)}}")
        if a.get("scope") == "privacy_allowlist":
            if not a.get("value_sha256") or not all(isinstance(h, str) and HEX64.match(h) for h in a["value_sha256"]):
                errs.append(f"{aid}: value_sha256 must be a non-empty list of exact sha256 hex values")
            if not a.get("categories") or not all(isinstance(c, str) for c in a["categories"]):
                errs.append(f"{aid}: categories must be a non-empty list")
    return errs


def github_get(path: str) -> dict:
    req = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json",
        "User-Agent": "myalpha-approval-verifier"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def evidence_errors(reg: dict, repo: str, fetch=github_get) -> list:
    errs = []
    for a in reg.get("approvals", []):
        ev, aid = a["evidence"], a["approval_id"]
        try:
            c = fetch(f"/repos/{repo}/issues/comments/{ev['comment_id']}")
        except Exception as e:  # fail closed: an approval we cannot verify is not an approval
            errs.append(f"{aid}: evidence comment {ev['comment_id']} could not be fetched ({type(e).__name__})")
            continue
        if not str(c.get("issue_url", "")).endswith(f"/repos/{repo}/issues/{ev['issue']}"):
            errs.append(f"{aid}: comment {ev['comment_id']} is not on {repo}#{ev['issue']}")
        if c.get("author_association") != "OWNER":
            errs.append(f"{aid}: comment {ev['comment_id']} is not by the repository owner")
        if ev["must_contain"] not in (c.get("body") or ""):
            errs.append(f"{aid}: comment {ev['comment_id']} does not contain the approval marker")
    return errs


def main(argv=None) -> int:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errs = schema_errors(reg)
    if not errs:
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not repo or not os.environ.get("GITHUB_TOKEN"):
            errs = ["GITHUB_REPOSITORY / GITHUB_TOKEN missing: approvals cannot be verified"]
        else:
            errs = evidence_errors(reg, repo)
    for e in errs:
        print(f"::error title=Owner approval::{e}")
    print(json.dumps({"approvals": len(reg.get("approvals", [])), "errors": len(errs)}))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
