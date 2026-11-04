#!/usr/bin/env python3
"""Verify every Owner approval in research/specs/retrieval/owner_approval_registry.json against GitHub (kr-0.3.2,
GPT #133 6624784358 B2/D4).

For each approval: the schema is exact, the scope is known, and its evidence comment exists on the named issue of
this repository, was written by the repository OWNER (author_association == "OWNER") and contains the entry's
`must_contain` marker. Any failure — including a network or permission error — exits 1. Read-only: one GET per
approval with the workflow's read-only GITHUB_TOKEN; nothing is written.

  python scripts/verify_owner_approvals.py [--registry PATH]   # needs GITHUB_TOKEN and GITHUB_REPOSITORY
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "research" / "specs" / "retrieval" / "owner_approval_registry.json"
COMMON = {"approval_id", "scope", "status", "granted_at", "evidence", "decision"}
SCOPE_KEYS = {"retrieval_production_eligibility": COMMON | {"kinds"},
              "privacy_allowlist": COMMON | {"categories", "value_sha256"}}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


TOP_KEYS = {"version", "rule", "scopes", "approvals"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _approval_capable_kinds() -> set:
    c = json.loads((ROOT / "research" / "specs" / "retrieval" / "eligibility_contract.json").read_text(encoding="utf-8"))
    return {k for k, v in c["kinds"].items() if v.get("approval_capable") is True}


def _privacy_categories() -> set:
    sys.path.insert(0, str(ROOT / "scripts"))
    import privacy_canary_scan as pcs  # noqa: E402
    return {name for name, _ in pcs.PATTERNS} | {"position_field"}


def _str_list(x, allowed: set) -> str | None:
    """None if x is a non-empty list of unique strings, all in allowed; otherwise the reason."""
    if not isinstance(x, list) or not x:
        return "must be a non-empty list"
    if not all(isinstance(v, str) and v for v in x):
        return "must contain only non-empty strings"
    if len(set(x)) != len(x):
        return "has duplicates"
    unknown = sorted(set(x) - allowed)
    return f"has unknown values {unknown}" if unknown else None


def schema_errors(reg) -> list:
    """Exact registry schema; anything malformed is an error (the caller fails closed)."""
    if not isinstance(reg, dict):
        return ["registry is not a JSON object"]
    errs, seen = [], set()
    if set(reg) != TOP_KEYS:
        errs.append(f"registry top-level keys {sorted(set(reg) ^ TOP_KEYS)} differ from {sorted(TOP_KEYS)}")
    if not isinstance(reg.get("version"), str) or not isinstance(reg.get("rule"), str):
        errs.append("version and rule must be strings")
    if not isinstance(reg.get("scopes"), list) or set(reg.get("scopes") or []) != set(SCOPE_KEYS) or len(reg.get("scopes") or []) != len(SCOPE_KEYS):
        errs.append("registry scopes differ from the known scopes")
    if not isinstance(reg.get("approvals"), list):
        return errs + ["approvals must be a list"]
    kinds_ok, cats_ok = _approval_capable_kinds(), _privacy_categories()
    for a in reg["approvals"]:
        if not isinstance(a, dict):
            errs.append("approval entry is not an object")
            continue
        aid = a.get("approval_id")
        if not isinstance(aid, str) or not re.fullmatch(r"OWNER-[A-Z0-9-]{4,60}", aid) or aid in seen:
            errs.append(f"bad or duplicate approval_id {aid!r}")
        seen.add(aid)
        want = SCOPE_KEYS.get(a.get("scope")) if isinstance(a.get("scope"), str) else None
        if want is None:
            errs.append(f"{aid}: unknown scope {a.get('scope')!r}")
            continue
        if set(a) != want:
            errs.append(f"{aid}: keys {sorted(set(a) ^ want)} differ from the {a['scope']} schema")
        if a.get("status") not in ("active", "revoked"):
            errs.append(f"{aid}: status must be active or revoked")
        g = a.get("granted_at")
        if not isinstance(g, str) or not DATE.match(g):
            errs.append(f"{aid}: granted_at must be YYYY-MM-DD")
        else:
            try:
                datetime.strptime(g, "%Y-%m-%d")
            except ValueError:
                errs.append(f"{aid}: granted_at is not a real date")
        if not isinstance(a.get("decision"), str) or len(a["decision"].strip()) < 10:
            errs.append(f"{aid}: decision must be a sentence (>= 10 chars)")
        ev = a.get("evidence") if isinstance(a.get("evidence"), dict) else {}
        if set(ev) != {"issue", "comment_id", "must_contain"} or not all(type(ev.get(k)) is int and ev[k] > 0 for k in ("issue", "comment_id")) \
                or not isinstance(ev.get("must_contain"), str) or len(ev["must_contain"]) < 8:
            errs.append(f"{aid}: evidence must be {{issue>0, comment_id>0, must_contain (>=8 chars)}}")
        if a["scope"] == "retrieval_production_eligibility":
            why = _str_list(a.get("kinds"), kinds_ok)
            if why:
                errs.append(f"{aid}: kinds {why}")
        if a["scope"] == "privacy_allowlist":
            why = _str_list(a.get("categories"), cats_ok)
            if why:
                errs.append(f"{aid}: categories {why}")
            hs = a.get("value_sha256")
            if not isinstance(hs, list) or not hs or len(set(hs)) != len(hs) or not all(isinstance(h, str) and HEX64.match(h) for h in hs):
                errs.append(f"{aid}: value_sha256 must be a non-empty list of unique exact sha256 hex values")
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
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[argv.index("--registry") + 1]) if "--registry" in argv else REGISTRY
    try:
        reg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # unreadable / malformed registry: fail closed
        print(f"::error title=Owner approval::registry {path.name} unreadable ({type(e).__name__})")
        return 1
    errs = schema_errors(reg)
    if not errs:
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not repo or not os.environ.get("GITHUB_TOKEN"):
            errs = ["GITHUB_REPOSITORY / GITHUB_TOKEN missing: approvals cannot be verified"]
        else:
            errs = evidence_errors(reg, repo)
    for e in errs:
        print(f"::error title=Owner approval::{e}")
    print(json.dumps({"registry": path.name, "approvals": len(reg.get("approvals", []) if isinstance(reg, dict) else []), "errors": len(errs)}))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
