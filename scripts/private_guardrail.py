#!/usr/bin/env python3
"""Public Leak Guard: fail-closed static scan for MyAlpha public artifacts.

Legacy filename retained for compatibility. This is not the planned private
capital/leverage guardrail.

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
PUBLIC_JSON_ROOT_ALLOWLIST = {
    "docs/research/server_action_status.json": {
        "version","generated_at","last_checked_at","status","judgment_basis","positions_checked","action_counts",
        "event_count_48h","quote_failures","option_learning","decision_learning",
        "data_trust","delivery","alert_fingerprint","privacy",
    },
    "docs/research/investment_actions_status.json": {
        "version","generated_at","module","freshness","gold","dca_calendar","alert_state","guardrails","learning",
    },
    "docs/research/auto_thesis_drafts.json": {
        "version","generated_at","mode","external_requests","symbols","counts","guardrails","revision_history_added",
    },
    "docs/research/system_status.json": {
        "version","generated_at","overall","principle","workflows","artifacts",
        "playbook_runtime","range_research","resource_guard","decision_data_contract",
    },
    "docs/research/official_evidence.json": {
        "version","generated_at","source","policy","selected_symbols","symbols",
        "counts","ticker_directory_status",
    },
    "docs/research/event_evidence.json": {
        "version","generated_at","source","policy","selected_symbols","symbols","counts",
    },
    "docs/research/autonomous_agent.json": {
        "version","generated_at","as_of","mode","attention_summary","watchlist_attention",
        "private_position_agent","discovery_queue","roadmap","guardrails",
    },
    "docs/research/research_execution.json": {
        "version","generated_at","planner_version","policy","results","summary",
    },
    "docs/research/controlled_learning_policy.json": {
        "version","generated_at","mode","automatic_orders","production_mutation",
        "max_abs_priority_delta","task_kind_priority_delta","playbook_validation_priority_bonus",
        "candidate_adjustments","change_log","forward_evidence","forward_learning_feedback",
        "replay_evidence","method_evidence_state","guardrails",
    },
    "docs/research/source_rule_lifecycle.json": {
        "version","generated_at","mode","source_reading_version","source_outcome_version",
        "counts","by_method","rules","guardrails",
    },
}
PRIVATE_FIELD_NAMES = {
    "broker_account_id","account_number","user_id","option_positions","private_positions",
    "ledger_records","access_token","refresh_token","api_key","secret_key",
}

SECRET_PATTERNS = (
    re.compile(r'ghp_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
)


def schema_findings(path: Path, text: str):
    rel=path.relative_to(ROOT).as_posix()
    allowed=PUBLIC_JSON_ROOT_ALLOWLIST.get(rel)
    if allowed is None or path.suffix.lower()!=".json":
        return []
    try:
        import json
        doc=json.loads(text)
    except Exception:
        return [f"invalid-json:{rel}"]
    if not isinstance(doc,dict):
        return [f"unexpected-json-root:{rel}"]
    extras=sorted(set(doc)-set(allowed))
    findings=[f"unexpected-public-root-key:{rel}:{k}" for k in extras]
    def walk(v,prefix=""):
        if isinstance(v,dict):
            for k,val in v.items():
                if str(k).lower() in PRIVATE_FIELD_NAMES:
                    findings.append(f"private-field-name:{rel}:{prefix}{k}")
                walk(val,prefix+str(k)+".")
        elif isinstance(v,list):
            for item in v:
                walk(item,prefix)
    walk(doc)
    return findings


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
            findings.extend(schema_findings(path,text))
    return sorted(set(findings))


def main():
    findings = scan()
    if findings:
        print("PUBLIC LEAK GUARD FAIL")
        for item in findings:
            print(item)
        raise SystemExit(1)
    print("PASS V6.10b Public Leak Guard: public artifacts contain no detected private ledger/account material")


if __name__ == "__main__":
    main()
