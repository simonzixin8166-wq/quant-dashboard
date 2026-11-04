#!/usr/bin/env python3
"""D3 (GPT #133 6621145320): the recursive privacy / canary scanner finds planted values in nested objects, arrays,
JSONL and logs; reports location + category + redacted snippet only (never the raw value); and does not flag
ordinary public research content (fixture of real phrasings + a sample of real docs/research files)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import privacy_canary_scan as pcs  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "privacy_canary"
NO_ALLOW = set()  # tests never rely on the Owner allowlist

# 1) positives: every category is found, at the right nested path
hits = pcs.scan_paths([FX / "positive_nested.json", FX / "positive_lines.jsonl", FX / "positive_build.log"], NO_ALLOW)
cats = {h["category"] for h in hits}
want = {"canary_token", "account_number", "position_amount", "email", "private_supabase", "private_ledger", "position_field"}
assert want <= cats, want - cats
locs = {h["location"] for h in hits}
assert any("records[0].nested.deep[0].text" in l for l in locs), locs          # nested object in array in object
assert any("records[3].claims[0][1].text" in l for l in locs), locs           # array inside array
assert any("[line 1].a.b[0]" in l for l in locs), locs                         # JSONL nested
assert any(l.endswith("positive_build.log:2") for l in locs), locs            # plain log line
assert any("records[7].holdings[0].qty" in l for l in locs), locs             # holding field by value
print(f"PASS positives: {len(hits)} hits, categories {sorted(cats)}")

# 2) redaction: no raw sensitive value appears in any reported snippet
raw = ["CANARY-7f3a9c21-4b6e-4d2a-9e11-0c55aa77bb01", "6228 4801 2345 6789 012", "real.person@gmail.com",
       "myalpha-ledger-private/blob", "$95,000", "9876543210", "1234-5678-9012", "options_positions"]
dump = json.dumps(hits, ensure_ascii=False)
assert not [r for r in raw if r in dump], [r for r in raw if r in dump]
print("PASS redaction: snippets never contain the raw value")

# 3) negatives: real public phrasings (prices, per-share figures, EPS, public edge-function URL, form placeholder)
neg = pcs.scan_paths([FX / "negative_public.json"], NO_ALLOW)
assert not neg, neg
# real public research files sampled from docs/research (third-party excerpts, propositions, SEC text)
sample = [ROOT / "docs/research" / n for n in ("source_reading_memory.json", "official_evidence.json", "event_evidence.json",
                                              "auto_thesis_drafts.json", "forward_scorecard.json", "core_tier_alert_status.json")]
real = pcs.scan_paths([p for p in sample if p.exists()], NO_ALLOW)
assert not real, real[:5]
print(f"PASS negatives: 0 hits on the public-phrasing fixture and on {sum(p.exists() for p in sample)} real docs/research files")

# 4) the CLI exits 1 on a hit and 0 on clean input (no warning-only mode)
assert pcs.main([str(FX / "positive_nested.json")]) == 1
assert pcs.main([str(FX / "negative_public.json")]) == 0
# 5) an allowlist entry without owner_approval never silences a hit
import hashlib, tempfile
tmp = Path(tempfile.mkdtemp()) / "allow.json"
tmp.write_text(json.dumps({"entries": [{"value_sha256": hashlib.sha256(b"real.person@gmail.com").hexdigest(), "owner_approval": None}]}))
assert any(h["category"] == "email" for h in pcs.scan_paths([FX / "positive_nested.json"], pcs.load_allowlist(tmp)))
print("PASS CLI exit codes and allowlist requires owner_approval")

# ---------------- kr-0.3.2 (GPT #133 6624784358 D3/D4) ----------------
import io, zipfile  # noqa: E402
T = Path(tempfile.mkdtemp())
EMPTY_REVIEW = set()

# 6) output carries only location + category: no part of the value, no length, no fingerprint
assert all(set(h) == {"location", "category"} for h in hits), hits[:2]

# 7) holdings without a dollar amount (quantity / option contracts / account) are found; prices and counts are not
pq = T / "pq.md"
pq.write_text("\n".join([
    "我持有 300 股 QQQM，打算继续拿",            # 1 quantity, no amount
    "my position: 5 NVDA 2027 calls",            # 2 option contracts
    "the account holds 20 contracts of SPY puts",  # 3 account + contracts
    "我的仓位 1,200 股 VGT",                      # 4
    "QQQM 股价 252.1，成交 300 万股",              # 5 price / market volume: not a holding
    "每张合约代表 100 股",                         # 6 contract definition: not a holding
    "Holders of 13F filings reported 5,000 shares", # 7 third-party report: not first person
]), encoding="utf-8")
got = {h["location"].rsplit(":", 1)[1] for h in pcs.scan_paths([pq], NO_ALLOW, reviewed=EMPTY_REVIEW) if h["category"] in ("position_quantity", "position_amount")}
assert got == {"1", "2", "3", "4"}, got
print("PASS holdings without amounts: 4 first-person/account holdings found, 3 market/definition lines not flagged")

# 8) fail closed: unreadable / undecodable / missing paths and broken ZIPs are hits, never silently skipped
(T / "bad.txt").write_bytes(b"\xff\xfe\x00broken")
(T / "broken.zip").write_bytes(b"PK\x03\x04garbage")
fc = pcs.scan_paths([T / "bad.txt", T / "broken.zip", T / "does_not_exist"], NO_ALLOW, reviewed=EMPTY_REVIEW)
assert [h["category"] for h in fc] == ["unscannable"] * 3, fc
# any suffix is scanned (config, source, extension-less): no suffix list decides what is clean
for name in ("x.py", "x.toml", "x.ini", "x.env", "x.sql", "Dockerfile", "x.ts", "x.yaml"):
    (T / name).write_text("token CANARY-7f3a9c21-4b6e-4d2a-9e11-0c55aa77bb01\n", encoding="utf-8")
    assert [h["category"] for h in pcs.scan_paths([T / name], NO_ALLOW, reviewed=EMPTY_REVIEW)] == ["canary_token"], name
print("PASS fail-closed: undecodable / broken zip / missing path -> unscannable; 8 extra formats scanned")

# 9) Actions-artifact style ZIPs are unpacked and scanned recursively (zip inside zip)
inner = io.BytesIO()
with zipfile.ZipFile(inner, "w") as z:
    z.writestr("logs/run.log", "ok\nnote CANARY-7f3a9c21-4b6e-4d2a-9e11-0c55aa77bb01\n")
outer = T / "artifact.zip"
with zipfile.ZipFile(outer, "w") as z:
    z.writestr("index/data.json", json.dumps({"a": [{"b": "acct no 1234-5678-9012"}]}))
    z.writestr("nested.zip", inner.getvalue())
az = pcs.scan_paths([outer], NO_ALLOW, reviewed=EMPTY_REVIEW)
assert {h["category"] for h in az} == {"canary_token", "account_number"}, az
assert any("artifact.zip!nested.zip!logs/run.log:2" in h["location"] for h in az), az
print("PASS artifacts: ZIP members (and a ZIP inside a ZIP) scanned recursively")

# 10) binaries cannot be text-scanned: an unreviewed image fails; the same bytes pass only once pinned by sha256
img = T / "chart.png"
img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
assert [h["category"] for h in pcs.scan_paths([img], NO_ALLOW, reviewed=EMPTY_REVIEW)] == ["binary_unreviewed"]
assert pcs.scan_paths([img], NO_ALLOW, reviewed={hashlib.sha256(img.read_bytes()).hexdigest()}) == []
img.write_bytes(img.read_bytes() + b"\x01")  # changed after review -> fails again
assert [h["category"] for h in pcs.scan_paths([img], NO_ALLOW, reviewed={hashlib.sha256(b'x').hexdigest()})] == ["binary_unreviewed"]
print("PASS binaries: unreviewed / changed images fail; reviewed exact sha256 passes")

# 11) allowlist: exact schema + an ACTIVE matching registry approval; silences only its own category and value
H = hashlib.sha256(b"real.person@gmail.com").hexdigest()
def allow_with(entry, approval):
    a, r = T / "a.json", T / "r.json"
    a.write_text(json.dumps({"entries": [entry]})); r.write_text(json.dumps({"approvals": [approval]}))
    return pcs.load_allowlist(a, r)
good_e = {"value_sha256": H, "category": "email", "approval_id": "OWNER-T", "purpose": "test"}
good_a = {"approval_id": "OWNER-T", "scope": "privacy_allowlist", "status": "active", "categories": ["email"], "value_sha256": [H]}
assert allow_with(good_e, good_a) == {H: "email"}
for bad_e, bad_a, why in [
        (dict(good_e, owner_approval={"x": 1}), good_a, "extra key"),
        ({k: v for k, v in good_e.items() if k != "approval_id"}, good_a, "no approval id"),
        (dict(good_e, approval_id="OWNER-OTHER"), good_a, "unknown approval"),
        (good_e, dict(good_a, status="revoked"), "revoked"),
        (good_e, dict(good_a, scope="retrieval_production_eligibility"), "wrong scope"),
        (good_e, dict(good_a, categories=["account_number"]), "category not approved"),
        (good_e, dict(good_a, value_sha256=[hashlib.sha256(b"other").hexdigest()]), "different value"),
        (dict(good_e, value_sha256="*"), good_a, "wildcard")]:
    assert allow_with(bad_e, bad_a) == {}, why
al = allow_with(good_e, good_a)
mixed = T / "mixed.md"
mixed.write_text("contact real.person@gmail.com\nalso other.person@gmail.com\n", encoding="utf-8")
left = pcs.scan_paths([mixed], al, reviewed=EMPTY_REVIEW)
assert [h["location"].rsplit(":", 1)[1] for h in left] == ["2"], left  # only the approved exact value is silenced
assert pcs.scan_paths([mixed], {H: "account_number"}, reviewed=EMPTY_REVIEW).__len__() == 2  # category must match too
# the real allowlist resolves to exactly one value (the Owner feedback address), category email
real_allow = pcs.load_allowlist()
assert list(real_allow.values()) == ["email"] and len(real_allow) == 1, real_allow
print("PASS allowlist: strict schema, active matching approval, same category, exact value only")

# 12) a scanner crash is a failure, never a pass
orig = pcs.scan_paths
pcs.scan_paths = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
try:
    assert pcs.main([str(FX / "negative_public.json")]) == 1
finally:
    pcs.scan_paths = orig
print("PASS scanner error -> exit 1")

# 13a) Owner 2026-11-04: Gemini screen-derived descriptions are not stored (they described a third party's on-screen
# account); the probe drops them and its validator refuses them; the whole research/ tree scans clean
gw = (WF_DIR := ROOT / ".github" / "workflows") / "gemini-youtube-probe.yml"
gt = gw.read_text(encoding="utf-8")
assert 'parsed.pop("visual_only_observations"' in gt and '"visual_only_observations" not in p["gemini_result"]' in gt
assert pcs.scan_paths([ROOT / "research"], pcs.load_allowlist()) == [], "research/ must scan clean before its artifact upload"

# 13) D4 wiring: every workflow that commits to the repo runs the --staged guard before its first `git commit`;
# the artifact uploads that are covered are gated on the guard; the uncovered ones are listed explicitly.
WF = ROOT / ".github" / "workflows"
NOT_COVERED_UPLOADS = {"autonomous-qa.yml": "uploads PNG screenshots (images cannot be text-scanned)",
                       "claude-audit-package.yml": "uploads a zip of the public repo itself, which contains the planted test canaries"}
committers = []
for w in sorted(WF.glob("*.yml")):
    t = w.read_text(encoding="utf-8")
    if "git commit" in t:
        committers.append(w.name)
        g, c = t.find("privacy_canary_scan.py --staged"), t.find("git commit")
        assert 0 <= g < c, f"{w.name}: publish guard missing before git commit"
    if "upload-artifact" in t and w.name not in NOT_COVERED_UPLOADS and w.name != "privacy-canary-gate.yml":
        assert "steps.privacy_guard.outcome == 'success'" in t, f"{w.name}: upload not gated by the privacy guard"
assert len(committers) == 11, committers
print(f"PASS D4 wiring: {len(committers)} committing workflows guarded before commit; uploads gated or listed as not covered ({len(NOT_COVERED_UPLOADS)}); research/ clean")
