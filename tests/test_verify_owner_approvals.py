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

# ---- kr-0.3.2 round 3 (GPT 6625522839 B2): exact types, enums and formats; malformed registries fail closed ----
r0 = copy.deepcopy(reg)
ret = {"approval_id": "OWNER-T-RET", "scope": "retrieval_production_eligibility", "kinds": ["rule"], "status": "active",
       "granted_at": "2026-11-04", "evidence": {"issue": 133, "comment_id": 1, "must_contain": "marker-123"},
       "decision": "test approval for schema checks"}
r0["approvals"].append(ret)
assert v.schema_errors(r0) == [], v.schema_errors(r0)
bad_kinds = [("rule", "string (substring match risk)"), (7, "number"), ([], "empty"), (["rule", "rule"], "duplicate"),
             (["no_such_kind"], "unknown kind"), (["incident"], "kind that is never approval-capable"), ([None], "null member")]
for kinds, why in bad_kinds:
    r = copy.deepcopy(r0); r["approvals"][-1]["kinds"] = kinds
    assert v.schema_errors(r), why
for field, val, why in [("granted_at", "2026-13-40", "impossible date"), ("granted_at", "yesterday", "not a date"),
                        ("granted_at", 20261104, "number date"), ("decision", "", "empty decision"), ("decision", None, "null decision"),
                        ("approval_id", "x", "id format"), ("scope", ["privacy_allowlist"], "scope as list")]:
    r = copy.deepcopy(r0); r["approvals"][-1][field] = val
    assert v.schema_errors(r), why
r = copy.deepcopy(r0); r["approvals"][0]["categories"] = "email"
assert v.schema_errors(r), "categories as string"
r = copy.deepcopy(r0); r["approvals"][0]["categories"] = ["not_a_category"]
assert v.schema_errors(r), "unknown category"
r = copy.deepcopy(r0); r["approvals"][-1]["evidence"]["comment_id"] = True
assert v.schema_errors(r), "bool comment id"
for malformed, why in [([], "list registry"), ({"approvals": []}, "missing top keys"), (dict(reg, extra=1), "extra top key"),
                       (dict(reg, approvals={}), "approvals not a list"), (dict(reg, approvals=["x"]), "approval not an object")]:
    assert v.schema_errors(malformed), why
import tempfile  # noqa: E402
bad_file = Path(tempfile.mkdtemp()) / "reg.json"
bad_file.write_text("{not json", encoding="utf-8")
assert v.main(["--registry", str(bad_file)]) == 1, "unreadable registry must fail"

# positive online path: a retrieval approval fixture passes schema + evidence; the eligibility evaluator then accepts the
# legal fixture rows with it, while the REAL registry still has no retrieval approval (real data stays 0 eligible)
online = json.loads((ROOT / "tests/fixtures/retrieval/approval_registry_online_fixture.json").read_text(encoding="utf-8"))
assert v.schema_errors(online) == [], v.schema_errors(online)
ev = online["approvals"][0]["evidence"]
assert v.evidence_errors(online, REPO, fake({"issue_url": f"https://api.github.com/repos/{REPO}/issues/{ev['issue']}",
                                             "author_association": "OWNER", "body": f"... {ev['must_contain']} ..."})) == []
import retrieval_eligibility as re_  # noqa: E402
C = re_.load_contract()
legal = [c for c in C["cases"] if c["expected"]]
for c in legal:
    row = dict(c["row"], owner_production_approval_id="OWNER-TEST-ONLINE-FIXTURE")
    assert re_.evaluate(c["kind"], row, C, online) == (True, None, []), c["kind"]
    assert re_.evaluate(c["kind"], row, C, re_.load_registry())[1] == "no_owner_approval"
assert not [a for a in re_.load_registry()["approvals"] if a["scope"] == "retrieval_production_eligibility"]
# a registry whose kinds is a string can no longer grant by substring
sub = copy.deepcopy(online); sub["approvals"][0]["kinds"] = "forward_observation_promoted"
assert re_.evaluate("forward_observation", dict(legal[0]["row"], owner_production_approval_id="OWNER-TEST-ONLINE-FIXTURE"), C, sub)[1] == "no_owner_approval"
print("PASS registry schema: 7 bad kinds, 7 bad fields, 2 bad categories, bool id, 5 malformed registries, unreadable file rejected; "
      "online positive fixture accepted (test only); real registry 0 retrieval approvals")
