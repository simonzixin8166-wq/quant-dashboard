#!/usr/bin/env python3
"""kr-0.3.2 (GPT #133 6624784358 B2/D4): Owner approvals are verified against the evidence comment, offline here with
a fake GitHub; the real check runs in privacy-canary-gate.yml with the read-only token."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_owner_approvals as v  # noqa: E402

REPO = "simonzixin8166-wq/quant-dashboard"
reg = json.loads(v.REGISTRY.read_text(encoding="utf-8"))
assert v.schema_errors(reg) == [], v.schema_errors(reg)
a0 = reg["approvals"][0]
GOOD = {"issue_url": f"https://api.github.com/repos/{REPO}/issues/133", "author_association": "OWNER",
        "body": f"... {a0['evidence']['must_contain']} ..."}


def fake(resp):
    def f(path):
        if isinstance(resp, Exception):
            raise resp
        return resp
    return f


assert v.evidence_errors(reg, REPO, fake(GOOD)) == []
for resp, why in [(dict(GOOD, author_association="CONTRIBUTOR"), "not owner"),
                  (dict(GOOD, issue_url=f"https://api.github.com/repos/{REPO}/issues/999"), "other issue"),
                  (dict(GOOD, body="no marker"), "marker missing"),
                  (OSError("network"), "fetch failed")]:
    assert v.evidence_errors(reg, REPO, fake(resp)), why

# schema is exact: extra / missing keys, unknown scope, bad hashes and weak evidence all fail
for mutate, why in [(lambda a: a.update(extra=1), "extra key"), (lambda a: a.pop("decision"), "missing key"),
                    (lambda a: a.update(scope="anything"), "unknown scope"), (lambda a: a.update(value_sha256=["*"]), "wildcard"),
                    (lambda a: a.update(status="maybe"), "bad status"),
                    (lambda a: a["evidence"].update(must_contain="x"), "weak marker"),
                    (lambda a: a["evidence"].update(comment_id=0), "no comment")]:
    r = copy.deepcopy(reg)
    mutate(r["approvals"][0])
    assert v.schema_errors(r), why
dup = copy.deepcopy(reg)
dup["approvals"].append(copy.deepcopy(dup["approvals"][0]))
assert v.schema_errors(dup), "duplicate id"
print(f"PASS owner approval verifier: {len(reg['approvals'])} registry approval(s); owner/issue/marker/fetch failures and 8 schema faults rejected")
