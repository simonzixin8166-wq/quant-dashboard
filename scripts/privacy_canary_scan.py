#!/usr/bin/env python3
"""Recursive privacy / canary scanner (contracts kr-0.3.2 §4.3; GPT #133 6621145320 D3/D4).

Walks every value of every JSON / JSONL document (nested objects and arrays included), and every line of text files,
and reports hits by file, JSON path or line, category and a REDACTED snippet. The sensitive value itself is never
printed. Exit code 1 on any hit that is not on the exact-value allowlist; there is no warning-only mode.

Categories:
  canary_token      CANARY-<hex/uuid> test markers
  account_number    account-like digit runs next to an account word (account / acct / 账户 / 账号 / 帐号 / 卡号)
  position_amount   a holding: holding word + held share/contract quantity + $ / USD amount (prices, per-share
                    figures and EPS lines are not holdings)
  email             e-mail addresses
  private_supabase  Supabase REST / service-role / private-table URLs (the public project root and its public
                    edge functions are served to every browser by design and are not secrets)
  private_ledger    links to the private ledger repository
  position_field    a JSON key that names a holding attribute (qty, shares, cost_basis, account_number, ...) with a
                    non-empty value

Allowlist: research/specs/retrieval/privacy_allowlist.json lists exact values (sha256 only) that the Owner approved
as intentionally public. Entries without owner_approval are ignored, so an unapproved entry never silences a hit.

  python scripts/privacy_canary_scan.py PATH [PATH ...]   # files or directories
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "research" / "specs" / "retrieval" / "privacy_allowlist.json"
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".html", ".js", ".mjs", ".css", ".csv", ".log", ".yml", ".yaml", ".xml", ".svg"}
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
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("private_supabase", re.compile(r"https?://[a-z0-9]+\.supabase\.co/(?:rest/v1|auth/v1/admin|storage/v1/object/(?!public))\S*|service_role", re.I)),
    ("private_ledger", re.compile(r"github\.com[/:][\w-]+/myalpha-ledger-private", re.I)),
]
POSITION_KEYS = {"qty", "quantity", "shares", "shares_held", "cost_basis", "avg_cost", "average_cost", "account",
                 "account_id", "account_number", "acct", "pnl", "unrealized_pnl", "realized_pnl", "premium_paid",
                 "strike_owned", "market_value", "holding", "holdings", "position_size", "contracts_held"}


def redact(s: str) -> str:
    s = s.strip()
    if len(s) <= 6:
        return s[:1] + "***"
    return f"{s[:3]}***{s[-2:]} (len {len(s)}, sha256 {hashlib.sha256(s.encode()).hexdigest()[:10]})"


def load_allowlist(path: Path = ALLOWLIST) -> set:
    if not path.exists():
        return set()
    d = json.loads(path.read_text(encoding="utf-8"))
    return {e["value_sha256"] for e in d.get("entries", []) if e.get("owner_approval")}


def scan_string(s: str, where: str, allow: set, out: list) -> None:
    for cat, rx in PATTERNS:
        for m in rx.finditer(s):
            v = m.group(0)
            core = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", v) if cat == "email" else None
            key = hashlib.sha256((core.group(0) if core else v).encode()).hexdigest()
            if key in allow:
                continue
            if cat == "email" and re.search(r"@(?:example\.(?:com|org|net)|email\.com)$|^(?:your|you|name|user)@", v, re.I):
                continue  # form placeholders such as your@email.com / name@example.com are not personal data
            out.append({"location": where, "category": cat, "snippet": redact(v)})


def walk(x, path: str, file: str, allow: set, out: list) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            p = f"{path}.{k}" if path else str(k)
            if str(k).lower() in POSITION_KEYS and v not in (None, "", [], {}, 0):
                out.append({"location": f"{file}::{p}", "category": "position_field", "snippet": f"key '{k}' with {type(v).__name__} value"})
            scan_string(str(k), f"{file}::{p}<key>", allow, out)
            walk(v, p, file, allow, out)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            walk(v, f"{path}[{i}]", file, allow, out)
    elif isinstance(x, str):
        scan_string(x, f"{file}::{path or '$'}", allow, out)


def scan_file(p: Path, allow: set, out: list, rel_to: Path | None = None) -> None:
    name = str(p.relative_to(rel_to)) if rel_to and p.is_relative_to(rel_to) else str(p)
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        return
    if p.suffix == ".json":
        try:
            walk(json.loads(txt), "", name, allow, out)
            return
        except Exception:
            pass
    if p.suffix == ".jsonl":
        ok = True
        for i, line in enumerate(txt.splitlines(), 1):
            if not line.strip():
                continue
            try:
                walk(json.loads(line), f"[line {i}]", name, allow, out)
            except Exception:
                ok = False
                scan_string(line, f"{name}:{i}", allow, out)
        if ok:
            return
        return
    for i, line in enumerate(txt.splitlines(), 1):
        scan_string(line, f"{name}:{i}", allow, out)


def scan_paths(paths, allow=None, rel_to: Path | None = ROOT) -> list:
    allow = load_allowlist() if allow is None else allow
    out = []
    for raw in paths:
        p = Path(raw)
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in TEXT_SUFFIXES) if p.exists() else []
        for f in files:
            scan_file(f.resolve(), allow, out, rel_to)
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: privacy_canary_scan.py PATH [PATH ...]")
        return 2
    hits = scan_paths(argv)
    cats = {}
    for h in hits:
        cats[h["category"]] = cats.get(h["category"], 0) + 1
    for h in hits[:200]:
        print(f"::error title=Privacy canary::{h['category']} at {h['location']} ({h['snippet']})")
    print(json.dumps({"scanned": argv, "hits": len(hits), "by_category": cats,
                      "scanner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, ensure_ascii=False))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
