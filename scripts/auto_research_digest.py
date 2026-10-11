#!/usr/bin/env python3
"""Public digest of the latest automatic-research session for the homepage row (#133 6109957428 P0-3).

Reads only research/knowledge/auto_research_journal.jsonl, docs/research/auto_research_status.json and
docs/research/module_failures.json (no network, nothing written to the journal). For the latest market session
in the journal it counts, per distinct symbol:
  new          hypotheses formed for that session (several same-session generator regenerations count once)
  invalidated  cross-day revisits whose invalidation condition fired
  abstained    symbols the job declined to judge
Same-session generator-upgrade "superseded" events are excluded everywhere: they are engineering, not research.
The detail list carries, per active hypothesis: stance, research/record date, supporting / opposing evidence
with source and as-of, invalidation conditions, next review, inputs and any append-only annotations.
SEC evidence produced before the SEC quality gate (#195/#196, generator auto-research-4) is flagged
`pre_sec_gate` so the page never presents it as current. Public, shadow-only data; no positions, no sizes.
Output: docs/research/auto_research_digest.json
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "research" / "knowledge" / "auto_research_journal.jsonl"
STATUS = ROOT / "docs" / "research" / "auto_research_status.json"
FAILURES = ROOT / "docs" / "research" / "module_failures.json"
OUT = ROOT / "docs" / "research" / "auto_research_digest.json"
SEC_GATE_GENERATOR = 4  # auto-research-4 introduced the SEC period/freshness/consistency gate


def gen_no(v):
    try:
        return int(str(v).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_engineering_supersede(r):
    return r.get("type") == "revisit" and str((r.get("trigger") or {}).get("reason", "")).startswith("generator upgrade")


def evidence(items, pre_gate):
    out = []
    for e in items or []:
        x = {k: e.get(k) for k in ("name", "group", "note", "source", "as_of", "available_at") if e.get(k) is not None}
        if pre_gate and e.get("group") == "fundamental":
            x["pre_sec_gate"] = True
        out.append(x)
    return out


def active(journal):
    closed = {r.get("hypothesis_id") for r in journal if r.get("type") == "revisit" and r.get("status") in ("invalidated", "superseded")}
    last = {}
    for r in journal:
        if r.get("type") == "hypothesis":
            last[r["symbol"]] = r
    return {s: h for s, h in last.items() if h["record_id"] not in closed}


def build(journal, status, failures, now=None):
    now = now or datetime.now(timezone.utc)
    research = [r for r in journal if r.get("type") in ("hypothesis", "revisit", "abstain")]
    latest = max((r["market_as_of"] for r in research), default=None)
    day = [r for r in research if r["market_as_of"] == latest and not is_engineering_supersede(r)]
    hyp_syms = sorted({r["symbol"] for r in day if r["type"] == "hypothesis"})
    inval = [r for r in day if r["type"] == "revisit" and r.get("status") == "invalidated"]
    xday = [r for r in day if r["type"] == "revisit"]
    abst = {}
    for r in day:
        if r["type"] == "abstain":
            abst[r["symbol"]] = r.get("decision_reason")
    notes = {}
    for r in journal:
        if r.get("type") == "annotation":
            notes.setdefault(r.get("annotates"), []).append({"kind": r.get("kind") or "timing", "note": r.get("note"),
                                                            "generated_at": r.get("generated_at")})
    act = active(journal)
    items = []
    for sym, h in sorted(act.items()):
        pre_gate = gen_no(h.get("generator_version")) < SEC_GATE_GENERATOR
        items.append({
            "symbol": sym, "stance": h.get("stance"), "hypothesis_id": h["record_id"],
            "market_as_of": h.get("market_as_of"), "research_date": h.get("research_date"), "generated_at": h.get("generated_at"),
            "generator_version": h.get("generator_version"), "decision_reason": h.get("decision_reason"),
            "research_hint": h.get("research_hint"),
            "supporting": evidence(h.get("supporting"), pre_gate), "opposing": evidence(h.get("opposing"), pre_gate),
            "opposing_note": h.get("opposing_note"),
            "invalidation": [x.get("note") or f"{x.get('metric')} {x.get('op')} {x.get('ref') or x.get('value')}" for x in h.get("invalidation") or []],
            "next_review": h.get("next_review"),
            "inputs": sorted((h.get("inputs") or {}).keys()),
            "unknowns": h.get("unknowns") or [],
            "pre_sec_gate": pre_gate,
            "annotations": notes.get(h["record_id"], []),
            "new_this_session": h.get("market_as_of") == latest,
        })
    st = status or {}
    fail = ((failures or {}).get("modules") or {}).get("auto_research") or {}
    last_run = st.get("last_run_at")
    failed_after = bool(fail.get("failed_at") and (not last_run or str(fail["failed_at"]) > str(last_run)))
    return {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "latest_session": latest,
        "counts": {"new": len(hyp_syms), "invalidated": len({r["symbol"] for r in inval}), "abstained": len(abst),
                   "revisited_cross_day": len({r["symbol"] for r in xday}),
                   "still_valid": len({r["symbol"] for r in xday if r.get("status") == "still_valid"}),
                   "superseded_cross_day": len({r["symbol"] for r in xday if r.get("status") == "superseded"}),
                   "review_due": len({r["symbol"] for r in xday if r.get("status") == "review_due"}),
                   "active": len(act)},
        "count_rules": "distinct symbols for the latest session; same-session generator-upgrade supersedes excluded",
        "new_symbols": hyp_syms,
        "invalidated": [{"symbol": r["symbol"], "hypothesis_id": r.get("hypothesis_id"),
                         "trigger": (r.get("trigger") or {}).get("note")} for r in inval],
        "abstained": [{"symbol": s, "reason": why} for s, why in sorted(abst.items())],
        "last_run": {"at": last_run, "run_id": st.get("last_run_id"), "generator_version": st.get("generator_version"),
                     "market_as_of": st.get("market_as_of")},
        "run_failure": {"failed_after_last_success": failed_after, "failed_at": fail.get("failed_at"), "run_id": fail.get("run_id")}
                       if fail else {"failed_after_last_success": False},
        "status_available": status is not None,
        "items": items,
        "learning_state": "UNPROVEN", "production_use": False, "shadow": True, "forward_eligible": False,
        "note": "shadow research hints, not orders; the owner decides and places every order manually",
    }


def main():
    journal = [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()] if JOURNAL.exists() else []
    d = build(journal, load_json(STATUS), load_json(FAILURES))
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = d["counts"]
    print(f"::notice title=Auto research digest::session={d['latest_session']} new={c['new']} invalidated={c['invalidated']} "
          f"abstained={c['abstained']} cross_day_revisits={c['revisited_cross_day']} active={c['active']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
