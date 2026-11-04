#!/usr/bin/env python3
"""Recursive privacy / canary scanner (contracts kr-0.3.2 §4.3; GPT #133 6621145320 D3/D4).

Walks every value of every JSON / JSONL document (nested objects and arrays included), every line of every other
file that decodes as UTF-8 (any suffix, no suffix list), and every member of ZIP archives (e.g. downloaded Actions
artifacts), recursively. Reports only file, location (JSON path or line) and category — never the value, a part of
it, its length or a fingerprint (kr-0.3.2, GPT #133 6624784358 D3). Exit code 1 on any hit not on the exact-value
allowlist; there is no warning-only mode.

Fail closed (category `unscannable`): a file that cannot be read, does not decode as UTF-8 and is not a reviewed
binary, a ZIP that cannot be opened, or a path that does not exist. Known binary formats (images, fonts, PDF) cannot
be text-scanned; each one must be listed with its exact sha256 in privacy_binary_review.json after a human looked
at it, otherwise it fails as `binary_unreviewed`. Free text that names a holding without the patterns below cannot
be proven absent by this scanner: such content needs human review and must not be published (see contracts §6.1).

Categories:
  canary_token      CANARY-<hex/uuid> test markers
  account_number    account-like digit runs next to an account word (account / acct / 账户 / 账号 / 帐号 / 卡号)
  position_amount   a holding: holding word + held share/contract quantity + $ / USD amount (prices, per-share
                    figures and EPS lines are not holdings)
  position_quantity a holding without an amount: first-person / account holding word + share or contract quantity
                    (e.g. "我持有 300 股 QQQM", "my position: 5 NVDA calls", "account holds 20 contracts")
  email             e-mail addresses
  private_supabase  Supabase REST / service-role / private-table URLs (the public project root and its public
                    edge functions are served to every browser by design and are not secrets)
  private_ledger    links to the private ledger repository
  position_field    a JSON key that names a holding attribute (qty, shares, cost_basis, account_number, ...) with a
                    non-empty value

Allowlist: research/specs/retrieval/privacy_allowlist.json lists exact values (sha256 only). An entry counts only if
its schema is exact and its approval_id names an ACTIVE privacy_allowlist approval in owner_approval_registry.json
that lists the same category and the same sha256 (CI verifies that approval against the Owner's #133 comment with
scripts/verify_owner_approvals.py). An allowlisted value silences only hits of its own category.

  python scripts/privacy_canary_scan.py PATH [PATH ...]   # files or directories
  python scripts/privacy_canary_scan.py --staged           # publish guard: the staged blobs the next git commit would publish
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "research" / "specs" / "retrieval"
ALLOWLIST = SPEC / "privacy_allowlist.json"
REGISTRY = SPEC / "owner_approval_registry.json"
BINARY_REVIEW = SPEC / "privacy_binary_review.json"
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pdf",
                   ".mp3", ".mp4", ".webm"}
SKIP_DIRS = {".git"}
ACCT_WORDS = r"(?:account|acct|账户|账号|帐号|帐户|卡号)"
PATTERNS = [
    ("canary_token", re.compile(r"CANARY-[0-9A-Fa-f]{8}(?:-?[0-9A-Fa-f]{4}){0,3}-?[0-9A-Fa-f]{0,12}")),
    ("account_number", re.compile(ACCT_WORDS + r"[\s#:：=_-]{0,12}(?:no\.?|number|号码)?[\s#:：=_-]{0,6}\d[\d\s-]{5,22}\d", re.I)),
    # a holding: a share / contract QUANTITY together with a money amount and a holding word, e.g.
    # "持有 300 股，成本 $95,000" / "my position: 20 contracts, $4,200". Prices ("股价 $16.77"), per-share
    # figures ("每股 $1", "$1000 per contract") and EPS lines carry no held quantity and are not holdings.
    ("position_amount", re.compile(
        r"(?:持有|持仓|仓位|建仓|加仓|my\s+position|positions?\s*:|holding|i\s+own|we\s+own|account\s+holds?)[^\n]{0,40}?"
        r"(?:(?<![\d.])\d[\d,]*\s*(?:股(?!价)|shares?\b|contracts?\b|张)[^\n]{0,40}?(?:\$|US\$|USD\s?)\s?\d[\d,]*(?:\.\d+)?"
        r"|(?:\$|US\$|USD\s?)\s?\d[\d,]*(?:\.\d+)?[^\n]{0,40}?(?<![\d.])\d[\d,]*\s*(?:股(?!价)|shares?\b|contracts?\b|张))", re.I)),
    ("position_quantity", re.compile(
        r"(?:我(?:的)?(?:持有|持仓|仓位|买入了?|建仓|加仓)|(?<![\w])(?:my|our)\s+(?:position|holding)s?\b|\bi\s+(?:own|hold|bought)\b|\bwe\s+(?:own|hold)\b|"
        r"account\s+holds?\b|账户(?:里|中)?(?:持有|有))[^\n]{0,30}?(?<![\d.])\d[\d,]*\s*(?:股(?!价)|shares?\b|contracts?\b|张|calls?\b|puts?\b)", re.I)),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("private_supabase", re.compile(r"https?://[a-z0-9]+\.supabase\.co/(?:rest/v1|auth/v1/admin|storage/v1/object/(?!public))\S*|service_role", re.I)),
    ("private_ledger", re.compile(r"github\.com[/:][\w-]+/myalpha-ledger-private", re.I)),
]
POSITION_KEYS = {"qty", "quantity", "shares", "shares_held", "cost_basis", "avg_cost", "average_cost", "account",
                 "account_id", "account_number", "acct", "pnl", "unrealized_pnl", "realized_pnl", "premium_paid",
                 "strike_owned", "market_value", "holding", "holdings", "position_size", "contracts_held"}


def load_allowlist(path: Path = ALLOWLIST, registry_path: Path = REGISTRY) -> dict:
    """{sha256: category} of approved exact values. Any schema deviation or an approval that does not match exactly
    makes the entry count for nothing (it never silences a hit)."""
    if not Path(path).exists():
        return {}
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    reg = json.loads(Path(registry_path).read_text(encoding="utf-8")) if Path(registry_path).exists() else {"approvals": []}
    approvals = {a.get("approval_id"): a for a in reg.get("approvals", [])}
    out = {}
    for e in d.get("entries", []):
        if set(e) != {"value_sha256", "category", "approval_id", "purpose"} or not re.fullmatch(r"[0-9a-f]{64}", str(e["value_sha256"])):
            continue
        a = approvals.get(e["approval_id"])
        if (a and a.get("status") == "active" and a.get("scope") == "privacy_allowlist"
                and e["category"] in (a.get("categories") or []) and e["value_sha256"] in (a.get("value_sha256") or [])):
            out[e["value_sha256"]] = e["category"]
    return out


def load_binary_review(path: Path = BINARY_REVIEW) -> set:
    if not Path(path).exists():
        return set()
    return {r["sha256"] for r in json.loads(Path(path).read_text(encoding="utf-8")).get("reviewed", [])}


def scan_string(s: str, where: str, allow: set, out: list) -> None:
    for cat, rx in PATTERNS:
        for m in rx.finditer(s):
            v = m.group(0)
            core = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", v) if cat == "email" else None
            key = hashlib.sha256((core.group(0) if core else v).encode()).hexdigest()
            if allow.get(key) == cat:  # exact value AND same category; dict form only
                continue
            if cat == "email" and re.search(r"@(?:example\.(?:com|org|net)|email\.com)$|^(?:your|you|name|user)@", v, re.I):
                continue  # form placeholders such as your@email.com / name@example.com are not personal data
            out.append({"location": where, "category": cat})


def walk(x, path: str, file: str, allow: set, out: list) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            p = f"{path}.{k}" if path else str(k)
            if str(k).lower() in POSITION_KEYS and v not in (None, "", [], {}, 0):
                out.append({"location": f"{file}::{p}", "category": "position_field"})
            scan_string(str(k), f"{file}::{p}<key>", allow, out)
            walk(v, p, file, allow, out)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            walk(v, f"{path}[{i}]", file, allow, out)
    elif isinstance(x, str):
        scan_string(x, f"{file}::{path or '$'}", allow, out)


def scan_text(txt: str, name: str, suffix: str, allow, out: list) -> None:
    if suffix == ".json":
        try:
            walk(json.loads(txt), "", name, allow, out)
            return
        except ValueError:
            pass  # not valid JSON: scanned line by line below
    if suffix == ".jsonl":
        for i, line in enumerate(txt.splitlines(), 1):
            if not line.strip():
                continue
            try:
                walk(json.loads(line), f"[line {i}]", name, allow, out)
            except ValueError:
                scan_string(line, f"{name}:{i}", allow, out)
        return
    for i, line in enumerate(txt.splitlines(), 1):
        scan_string(line, f"{name}:{i}", allow, out)


def scan_bytes(data: bytes, name: str, suffix: str, allow, out: list, reviewed: set, stats: dict) -> None:
    suffix = suffix.lower()
    if suffix == ".zip" or data[:4] == b"PK\x03\x04":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            members = [m for m in z.infolist() if not m.is_dir()]
        except (zipfile.BadZipFile, OSError):
            out.append({"location": name, "category": "unscannable"})
            return
        stats["zip_members"] += len(members)
        for m in members:
            try:
                inner = z.read(m)
            except Exception:
                out.append({"location": f"{name}!{m.filename}", "category": "unscannable"})
                continue
            scan_bytes(inner, f"{name}!{m.filename}", Path(m.filename).suffix, allow, out, reviewed, stats)
        return
    if suffix in BINARY_SUFFIXES:
        stats["binary_reviewed" if hashlib.sha256(data).hexdigest() in reviewed else "binary_unreviewed"] += 1
        if hashlib.sha256(data).hexdigest() not in reviewed:
            out.append({"location": name, "category": "binary_unreviewed"})
        return
    try:
        txt = data.decode("utf-8")
    except UnicodeDecodeError:
        out.append({"location": name, "category": "unscannable"})
        return
    stats["text_files"] += 1
    scan_text(txt, name, suffix, allow, out)


def scan_file(p: Path, allow, out: list, rel_to: Path | None = None, reviewed: set | None = None, stats: dict | None = None) -> None:
    name = str(p.relative_to(rel_to)) if rel_to and p.is_relative_to(rel_to) else str(p)
    stats = stats if stats is not None else new_stats()
    try:
        data = p.read_bytes()
    except OSError:
        out.append({"location": name, "category": "unscannable"})
        return
    scan_bytes(data, name, p.suffix, allow, out, load_binary_review() if reviewed is None else reviewed, stats)


def new_stats() -> dict:
    return {"text_files": 0, "zip_members": 0, "binary_reviewed": 0, "binary_unreviewed": 0, "missing_paths": 0}


def scan_paths(paths, allow=None, rel_to: Path | None = ROOT, stats: dict | None = None, reviewed: set | None = None) -> list:
    allow = load_allowlist() if allow is None else allow
    if isinstance(allow, set):  # tests may pass a plain set of hashes: it never silences anything without a category
        allow = {}
    reviewed = load_binary_review() if reviewed is None else reviewed
    stats = stats if stats is not None else new_stats()
    out = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            stats["missing_paths"] += 1
            out.append({"location": str(raw), "category": "unscannable"})  # a path we were told to scan must exist
            continue
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file() and not (SKIP_DIRS & set(f.parts)))
        for f in files:
            scan_file(f.resolve(), allow, out, rel_to, reviewed, stats)
    return out


def staged_entries() -> list:
    """[(path, mode, blob_sha, status)] of what the next `git commit` would publish, from the INDEX (not the worktree)."""
    import subprocess
    raw = subprocess.run(["git", "diff", "--cached", "--raw", "-z", "--no-renames", "--diff-filter=ACMRT"],
                         check=True, capture_output=True).stdout.decode("utf-8")
    parts = [x for x in raw.split("\0")]
    out, i = [], 0
    while i < len(parts) - 1:
        meta = parts[i]
        if not meta.startswith(":"):
            i += 1
            continue
        _, new_mode, _, new_sha, status = meta[1:].split(" ")[:5]
        out.append((parts[i + 1], new_mode, new_sha, status[:1]))
        i += 2
    return out


def scan_staged() -> int:
    """kr-0.3.2 D4-1 (GPT #133 6626194723): scan the staged BLOBS that will be committed. Symlinks, submodules and any
    mode other than a regular file fail closed, as does any git error."""
    import subprocess
    try:
        entries = staged_entries()
    except Exception as e:
        print(f"::error title=Privacy canary::cannot list staged blobs ({type(e).__name__}); publish blocked")
        return 1
    if not entries:
        print(json.dumps({"scanned": "staged index", "hits": 0, "note": "nothing staged"}))
        return 0
    allow, reviewed, stats, hits = load_allowlist(), load_binary_review(), new_stats(), []
    try:
        cat = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        for path, mode, sha, status in entries:
            if mode not in ("100644", "100755"):  # 120000 symlink, 160000 submodule, anything else: not scannable
                hits.append({"location": path, "category": "unscannable"})
                continue
            cat.stdin.write((sha + "\n").encode()); cat.stdin.flush()
            head = cat.stdout.readline().split()
            if len(head) != 3 or head[1] != b"blob":
                hits.append({"location": path, "category": "unscannable"})
                continue
            data = cat.stdout.read(int(head[2])); cat.stdout.read(1)
            scan_bytes(data, path, Path(path).suffix, allow, hits, reviewed, stats)
        cat.stdin.close(); cat.wait()
    except Exception as e:
        print(f"::error title=Privacy canary::scanner error {type(e).__name__}; publish blocked")
        return 1
    for h in hits[:200]:
        print(f"::error title=Privacy canary::{h['category']} at {h['location']} (staged)")
    cats = {}
    for h in hits:
        cats[h["category"]] = cats.get(h["category"], 0) + 1
    print(json.dumps({"scanned": f"{len(entries)} staged blobs (index content)", "hits": len(hits), "by_category": cats,
                      "coverage": stats, "scanner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))
    return 1 if hits else 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: privacy_canary_scan.py PATH [PATH ...] | --staged")
        return 2
    if argv == ["--staged"]:
        return scan_staged()
    stats = new_stats()
    try:
        hits = scan_paths(argv, stats=stats)
    except Exception as e:  # the scanner itself failing must never let a publish through
        print(f"::error title=Privacy canary::scanner error {type(e).__name__}")
        return 1
    cats = {}
    for h in hits:
        cats[h["category"]] = cats.get(h["category"], 0) + 1
    for h in hits[:200]:
        print(f"::error title=Privacy canary::{h['category']} at {h['location']}")
    print(json.dumps({"scanned": argv if len(argv) <= 20 else f"{len(argv)} paths", "hits": len(hits), "by_category": cats, "coverage": stats,
                      "not_covered": "image/font/PDF content (manual review, pinned by sha256); holdings written in free text without the listed patterns",
                      "scanner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, ensure_ascii=False))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
