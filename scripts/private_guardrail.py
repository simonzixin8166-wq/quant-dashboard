#!/usr/bin/env python3
"""Fail-closed static guard for MyAlpha public artifacts.

The public repository may contain sanitized status/anchors, but never raw
account, brokerage-position, token, or Forward-Ledger material.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOTS = (ROOT / "docs", ROOT / "config")
TEXT_SUFFIXES = {".json", ".jsonl", ".html", ".js", ".css", ".md", ".txt", ".csv"}
FORBIDDEN_KEYS = re.compile(r'"(?:option_positions|private_positions|broker_account_id|account_number|ledger_records)"\s*:', re.I)
SECRET_PATTERNS = (
    re.compile(r'ghp_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
)


def scan():
    findings = []
    for root in PUBLIC_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if "/ledger/" in f"/{rel}/" or path.suffix.lower() == ".jsonl":
                findings.append(f"raw-ledger-path:{rel}")
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if FORBIDDEN_KEYS.search(text):
                findings.append(f"private-key-material:{rel}")
            if any(p.search(text) for p in SECRET_PATTERNS):
                findings.append(f"secret-pattern:{rel}")
    return sorted(set(findings))


def main():
    findings = scan()
    if findings:
        print("PRIVATE GUARDRAIL FAIL")
        for item in findings:
            print(item)
        raise SystemExit(1)
    print("PASS V6.10b Private Guardrail: public artifacts contain no detected private ledger/account material")


if __name__ == "__main__":
    main()
