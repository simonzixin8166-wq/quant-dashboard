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
NOT_COVERED_UPLOADS = {}  # round 3: every upload is guarded (claude-audit-package by an exact tracked-tree check)
committers = []
for w in sorted(WF.glob("*.yml")):
    t = w.read_text(encoding="utf-8")
    if "git commit" in t:
        committers.append(w.name)
        g, c = t.find("privacy_canary_scan.py --staged"), t.find("git commit")
        assert 0 <= g < c, f"{w.name}: publish guard missing before git commit"
    if ("upload-artifact" in t or "upload-pages-artifact" in t) and w.name not in NOT_COVERED_UPLOADS and w.name != "privacy-canary-gate.yml":
        assert "steps.privacy_guard.outcome == 'success'" in t, f"{w.name}: upload not gated by the privacy guard"
assert len(committers) == 11, committers
print(f"PASS D4 wiring: {len(committers)} committing workflows guarded before commit; uploads gated or listed as not covered ({len(NOT_COVERED_UPLOADS)}); research/ clean")


# 14) round 3 (GPT 6625522839 D4): workflow-level negatives. The REAL guard step text is extracted from each workflow
# and run against a planted canary at that workflow's actual upload / download path; it must exit non-zero, and the
# upload (or staging) step must come after it and depend on it.
import subprocess  # noqa: E402


def steps_of(wf_text: str) -> list:
    """[(name, id, if, run)] for every `- name:` step, run = literal block or single line."""
    out, lines = [], wf_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)- name: (.*)$", lines[i])
        if not m:
            i += 1
            continue
        ind, name, sid, cond, run = len(m.group(1)), m.group(2).strip(), None, None, None
        j = i + 1
        while j < len(lines) and not re.match(rf"^\s{{{ind}}}- ", lines[j]) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > ind):
            l = lines[j].strip()
            if l.startswith("id:"):
                sid = l[3:].strip()
            elif l.startswith("if:"):
                cond = l[3:].strip()
            elif l.startswith("run: |"):
                k, body, bind = j + 1, [], len(lines[j]) - len(lines[j].lstrip()) + 2
                while k < len(lines) and (not lines[k].strip() or len(lines[k]) - len(lines[k].lstrip()) >= bind):
                    body.append(lines[k][bind:]); k += 1
                run = "\n".join(body)
            elif l.startswith("run:"):
                run = l[4:].strip()
            j += 1
        out.append((name, sid, cond, run))
        i = j
    return out


import re  # noqa: E402
CAN = "CANARY-7f3a9c21-4b6e-4d2a-9e11-0c55aa77bb01"
for wf, guard_id, plant, gated in [
        ("monthly-evidence-audit.yml", "privacy_guard", "research/x/out.json", "Package monthly research artifacts"),
        ("research-evidence-update.yml", "privacy_guard", "research/x/out.json", "Package research artifacts"),
        ("monthly-evidence-audit.yml", "privacy_guard_download", "research/x/out.json", "Commit monthly audit only"),
        ("research-evidence-update.yml", "privacy_guard_download", "research/x/out.json", "Commit research artifacts only"),
        ("autonomous-qa.yml", "privacy_guard", "qa-artifacts/report.json", "Upload sanitized QA report (no screenshots)"),
        ("trend-pulse-backtest.yml", "privacy_guard", "docs/research/trend_pulse_backtest.json", "Upload research artifact")]:
    st = steps_of((WF / wf).read_text(encoding="utf-8"))
    names = [x[0] for x in st]
    g = next(i for i, x in enumerate(st) if x[1] == guard_id)
    u = names.index(gated)
    assert g < u, (wf, guard_id, "guard must run before", gated)
    if guard_id == "privacy_guard":
        assert f"steps.{guard_id}.outcome == 'success'" in (st[u][2] or ""), (wf, gated, st[u][2])
    for planted_value, want_rc in ((CAN, 1), ("ok", 0)):
        work = Path(tempfile.mkdtemp())
        (work / "scripts").mkdir()
        (work / "scripts" / "privacy_canary_scan.py").write_bytes((ROOT / "scripts" / "privacy_canary_scan.py").read_bytes())
        f = work / plant
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"a": [{"note": planted_value}]}), encoding="utf-8")
        if wf == "autonomous-qa.yml":
            (work / "qa-artifacts" / "desktop-home.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # removed before the scan
        r = subprocess.run(["bash", "-e", "-c", st[g][3]], cwd=work, capture_output=True, text=True)
        assert (r.returncode != 0) == bool(want_rc), (wf, guard_id, planted_value, r.returncode, r.stdout[-300:], r.stderr[-300:])
        if wf == "autonomous-qa.yml":
            assert not (work / "qa-artifacts" / "desktop-home.png").exists(), "screenshots must not be uploaded"
print("PASS workflow-level negatives: monthly / research-evidence (upload + post-download), autonomous-qa and trend-pulse "
      "guards block a planted canary and pass clean output; uploads depend on the guard")

# 15) claude-audit-package: the upload is gated on an exact "package == tracked tree of the named commit" check
st = steps_of((WF / "claude-audit-package.yml").read_text(encoding="utf-8"))
byname = {x[0]: x for x in st}
create, verify = byname["Create complete main ZIP"][3], byname["Verify the package is exactly the public tracked tree"][3]
assert "steps.privacy_guard.outcome == 'success'" in (byname["Upload Claude audit package"][2] or "")
work = Path(tempfile.mkdtemp()) / "repo"
subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(work)], check=True)
ok = subprocess.run(["bash", "-e", "-c", create + "\n" + verify], cwd=work, capture_output=True, text=True)
assert ok.returncode == 0, ok.stdout[-400:] + ok.stderr[-400:]
(work / "zz_untracked_runtime.json").write_text('{"private": true}', encoding="utf-8")
subprocess.run(["zip", "-q", "MyAlpha_View_main_Claude_Audit.zip", "zz_untracked_runtime.json"], cwd=work, check=True)
bad = subprocess.run(["bash", "-e", "-c", verify], cwd=work, capture_output=True, text=True)
assert bad.returncode != 0, "an extra (untracked) file in the audit package was not detected"
print("PASS claude-audit-package: package equals the tracked tree; an extra file blocks the upload")


# 16) GPT #133 6626194723 final D4 items
# D4-1: --staged scans the INDEX blobs that will be committed, not the worktree; symlinks / type changes fail closed
def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True)


def guard(repo):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "privacy_canary_scan.py"), "--staged"], cwd=repo,
                          capture_output=True, text=True)


repo = Path(tempfile.mkdtemp())
git(repo, "init", "-q"); git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
(repo / "base.txt").write_text("base\n"); git(repo, "add", "base.txt"); git(repo, "commit", "-qm", "base")
leak = repo / "docs" / "data.json"
leak.parent.mkdir()
leak.write_text(json.dumps({"x": CAN}), encoding="utf-8")
git(repo, "add", "docs/data.json")
leak.write_text('{"x": "clean worktree"}', encoding="utf-8")       # worktree cleaned AFTER staging the leak
r = guard(repo)
assert r.returncode == 1 and "canary_token at docs/data.json" in r.stdout, r.stdout + r.stderr
assert CAN not in r.stdout + r.stderr
git(repo, "add", "docs/data.json")                                   # now the index holds the clean version
assert guard(repo).returncode == 0
leak.write_text(json.dumps({"x": CAN}), encoding="utf-8")           # dirty worktree, clean index -> passes (index is what ships)
assert guard(repo).returncode == 0
git(repo, "checkout", "--", "docs/data.json")
git(repo, "commit", "-qm", "clean")
(repo / "link.json").symlink_to("docs/data.json"); git(repo, "add", "link.json")
r = guard(repo)
assert r.returncode == 1 and "unscannable at link.json" in r.stdout, r.stdout
git(repo, "rm", "-q", "--cached", "link.json"); (repo / "link.json").unlink()
(repo / "base.txt").unlink(); (repo / "base.txt").symlink_to("docs/data.json"); git(repo, "add", "base.txt")  # type change
r = guard(repo)
assert r.returncode == 1 and "unscannable at base.txt" in r.stdout, r.stdout
print("PASS D4-1: --staged scans index blobs (leak staged then worktree cleaned -> blocked); symlink / type change fail closed")

# D4-2: trend-pulse scans exactly the files it uploads; a canary only in trend_pulse_summary.csv blocks the upload
tw = (WF / "trend-pulse-backtest.yml").read_text(encoding="utf-8")
up_block = tw[tw.index("- name: Upload research artifact"):]
uploaded = re.findall(r"^\s+(docs/research/\S+)$", up_block.split("\n      - ")[0], re.M)
gsteps = {x[0]: x for x in steps_of(tw)}
scanned = re.findall(r"docs/research/\S+?(?=[\s;])", gsteps["Privacy guard before upload (kr-0.3.2 D4)"][3])
assert len(uploaded) == 4 and set(uploaded) == set(scanned), (uploaded, scanned)
work = Path(tempfile.mkdtemp())
(work / "scripts").mkdir()
(work / "scripts" / "privacy_canary_scan.py").write_bytes((ROOT / "scripts" / "privacy_canary_scan.py").read_bytes())
(work / "docs" / "research").mkdir(parents=True)
for f in uploaded:
    (work / f).write_text("ok\n", encoding="utf-8")
(work / "docs/research/trend_pulse_summary.csv").write_text(f"symbol,note\nQQQ,{CAN}\n", encoding="utf-8")
r = subprocess.run(["bash", "-e", "-c", gsteps["Privacy guard before upload (kr-0.3.2 D4)"][3]], cwd=work, capture_output=True, text=True)
assert r.returncode != 0 and "trend_pulse_summary.csv" in r.stdout, r.stdout
print("PASS D4-2: trend-pulse scan list == upload list (4 files); canary only in trend_pulse_summary.csv blocks the upload")

# D4-3: wenxuecity publish-pages (runs only when vars.WXC_DEPLOY_PAGES == 'true') scans docs/ before upload + deploy
ww = (WF / "wenxuecity.yml").read_text(encoding="utf-8")
job = ww[ww.index("  publish-pages:"):]
assert "vars.WXC_DEPLOY_PAGES == 'true'" in job.split("\n")[1], "publish-pages must be the WXC_DEPLOY_PAGES path"
js = steps_of(job)
names = [x[0] for x in js]
gi = names.index("Privacy guard on the Pages publish directory (kr-0.3.2 D4)")
ui, di = names.index("Upload Pages artifact"), names.index("Deploy Pages")
assert gi < ui < di and all(js[i][2] == "steps.privacy_guard.outcome == 'success'" for i in (ui, di)), js
pages_path = re.search(r"upload-pages-artifact@v\d+\n\s+with:\n\s+path:\s*(\S+)", job).group(1)
assert js[gi][3].split()[-1] == pages_path == "docs", (js[gi][3], pages_path)
for content, want_fail in ((CAN, True), ("ok", False)):
    work = Path(tempfile.mkdtemp())
    (work / "scripts").mkdir()
    (work / "scripts" / "privacy_canary_scan.py").write_bytes((ROOT / "scripts" / "privacy_canary_scan.py").read_bytes())
    (work / "docs" / "research").mkdir(parents=True)
    (work / "docs" / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (work / "docs" / "research" / "wenxuecity.json").write_text(json.dumps({"posts": [{"t": content}]}), encoding="utf-8")
    r = subprocess.run(["bash", "-e", "-c", js[gi][3]], cwd=work, capture_output=True, text=True)
    assert (r.returncode != 0) == want_fail, (content, r.returncode, r.stdout[-300:])
print("PASS D4-3: WXC_DEPLOY_PAGES publish path scans docs/ before upload-pages-artifact and deploy-pages; a canary blocks both")
