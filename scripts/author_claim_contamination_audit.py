#!/usr/bin/env python3
"""Read-only impact audit + append-only quarantine for unverified author self-reported trades (#133 6117163110 P0-A).

Traces legacy author-operation attributions (wxc-bot keyword rules: an action word plus any first-person "我…"
in context → author_action) through every downstream path:
  source_intelligence (operation_cases / owned_operation_cases / failure_review)
  → source_outcome_validation events → evidence_attribution external_outcome_reviews / failure candidates
  → V6 planner / executor / self_improvement / controlled_learning_policy / method_memory / evidence engines.
For each path it records whether it can change research priority, error-attribution conclusions or weights,
and whether that path is gated (fail-closed). Affected records are written as append-only quarantine events
(one per record key; re-runs never duplicate, never edit or delete raw data). An author's own account of a trade
is never "verified": at most "compatible with market data".
Outputs: research/audit/author_claim_contamination.json, research/audit/author_claim_quarantine.jsonl
"""
from __future__ import annotations
import hashlib, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "docs" / "research"
SRC = ROOT / "docs" / "data" / "source_intelligence.json"
OUT = ROOT / "research" / "audit" / "author_claim_contamination.json"
QUAR = ROOT / "research" / "audit" / "author_claim_quarantine.jsonl"
CASE = "66b4cef06a84cd3de2eb"  # BrightLine 202610/7180 — legacy "TSLA sell / NVDA sell", ce-5 found no claim


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def src_text(name):
    p = ROOT / "scripts" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def gate_status():
    ev, mm = load(RES / "evidence_attribution.json"), load(RES / "method_memory.json")
    ex, ee, oe = src_text("autonomous_research_executor.py"), src_text("event_evidence_engine.py"), src_text("official_evidence_engine.py")
    legacy_ev = ev.get("external_outcome_evidence_role") == "legacy_descriptive_only"
    legacy_mm = mm.get("evidence_role") == "legacy_descriptive_only"
    return [
        {"path": "planner failure_review tasks", "can_change": "research priority", "gated": legacy_ev,
         "how": "evidence_attribution.external_outcome_evidence_role == legacy_descriptive_only → no tasks"},
        {"path": "self_improvement process_guardrail", "can_change": "research process policy", "gated": legacy_ev,
         "how": "same flag → failure count treated as 0"},
        {"path": "controlled_learning_policy / self_improvement method deltas", "can_change": "planner ±5 priority", "gated": legacy_mm,
         "how": "method_memory.evidence_role == legacy_descriptive_only → no deltas"},
        {"path": "executor market/failure briefs", "can_change": "counter-evidence / failure conclusions in V6 briefs",
         "gated": "外部研究反例/失效样本\")" not in ex and "未经核实，仅作背景" in ex,
         "how": "rows reported under unknowns as unverified background, never counter-evidence"},
        {"path": "event/official evidence symbol selection", "can_change": "which symbols get evidence collected",
         "gated": all('learning_eligible") is True' in t for t in (ee, oe)),
         "how": "only rows with learning_eligible == true (none today)"},
        {"path": "event_window_attribution rows (executor failure briefs)", "can_change": "failure-review context",
         "gated": "learning_eligible\":r.get(\"learning_eligible\") is True" in src_text("event_window_attribution.py")
                  and "未经核实的作者自述样本" in ex,
         "how": "rows carry verification_status / learning_eligible; executor reports them under unknowns"},
        {"path": "method_memory direct performance (display / knowledge page)", "can_change": "displayed method performance only",
         "gated": legacy_mm, "how": "evidence_role legacy_descriptive_only; consumers above ignore it for weights"},
    ]


def key(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:20]


def build(now=None):
    now = now or datetime.now(timezone.utc)
    src = load(SRC)
    val = load(RES / "source_outcome_validation.json")
    ev = load(RES / "evidence_attribution.json")
    ex = load(RES / "research_execution.json")
    events = val.get("events") or []
    reviews = ((ev.get("failure_attribution") or {}).get("external_outcome_reviews")) or []
    fcand = ((ev.get("failure_attribution") or {}).get("external_failure_candidates")) or []
    briefs = [{"task_id": r.get("task_id"), "symbol": r.get("key") or r.get("symbol"), "line": x}
              for r in (ex.get("results") or []) for x in (r.get("counter_evidence") or []) + (r.get("supporting_evidence") or [])
              if "Failure Attribution" in str(x) or "失败/反例样本" in str(x)]
    case = {"record_id": CASE,
            "in_operation_cases": any(r.get("id") == CASE for r in src.get("operation_cases") or []),
            "in_owned_operation_cases": any(r.get("id") == CASE for r in src.get("owned_operation_cases") or []),
            "in_failure_review": any(r.get("id") == CASE for r in src.get("failure_review") or []),
            "in_source_outcome_validation": any(CASE in str(e.get("event_id")) or e.get("url", "").endswith("7180.html") for e in events),
            "in_external_failure_candidates": any(r.get("id") == CASE for r in fcand),
            "note": "legacy rule labelled TSLA sell author_action/high and NVDA sell needs_review; ce-5 high-precision extraction found 0 claims; "
                    "the original page is not reachable by the audit tooling, so the author's actual trades are UNKNOWN — neither confirmed nor denied"}
    affected = []
    for e in events:
        if e.get("attribution") in {"author_action", "author_plan", "unconfirmed_author_context"}:
            affected.append({"kind": "source_outcome_event", "id": e.get("event_id"), "author": e.get("author"), "symbol": e.get("symbol"),
                             "attribution": e.get("attribution"), "attribution_confidence": e.get("attribution_confidence"),
                             "published_at": e.get("published_at")})
    for r in reviews:
        affected.append({"kind": "external_outcome_review", "id": r.get("event_id"), "author": r.get("author"), "symbol": r.get("symbol"),
                         "attribution": r.get("attribution"), "published_at": r.get("published_at")})
    for r in fcand:
        affected.append({"kind": "external_failure_candidate", "id": r.get("id"), "author": r.get("author"),
                         "symbol": ",".join(r.get("symbols") or []), "published_at": r.get("published_at")})
    for b in briefs:
        affected.append({"kind": "v6_brief_citation", "id": b["task_id"], "symbol": b["symbol"], "line": b["line"]})
    gates = gate_status()
    return {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rule": "author self-reported trades are never broker-verified; unverified attributions may be labelled background only",
        "counts": {"source_outcome_events": len(events),
                   "events_by_attribution": dict(Counter(f"{e.get('attribution')}/{e.get('attribution_confidence')}" for e in events)),
                   "events_by_author": dict(Counter(e.get("author") for e in events)),
                   "external_outcome_reviews": len(reviews), "external_failure_candidates": len(fcand),
                   "v6_brief_citations_before_gate": len(briefs), "affected_records": len(affected)},
        "gates": gates, "all_gated": all(g["gated"] is True for g in gates),
        "case_brightline_7180": case, "v6_brief_citations": briefs, "affected": affected,
        "read_only": True, "production_use": False,
    }


def append_quarantine(rep):
    known = set()
    if QUAR.exists():
        for line in QUAR.read_text(encoding="utf-8").splitlines():
            try:
                known.add(json.loads(line)["quarantine_key"])
            except Exception:
                pass
    new = []
    for a in rep["affected"]:
        k = key(a["kind"], a.get("id"), a.get("symbol"))
        if k in known:
            continue
        new.append({"quarantine_key": k, "event": "quarantine", "at": rep["generated_at"], **a,
                    "status": "unverified_author_self_report", "learning_eligible": False,
                    "reason": "legacy keyword attribution; never broker-verified; background context only (#133 6117163110 P0-A)"})
        known.add(k)
    if new:
        QUAR.parent.mkdir(parents=True, exist_ok=True)
        with QUAR.open("a", encoding="utf-8") as fh:
            for r in new:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return len(new)


def main():
    rep = build()
    rep["quarantine_appended"] = append_quarantine(rep)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = rep["counts"]
    print(f"::notice title=Author-claim gate::all_gated={rep['all_gated']} events={c['source_outcome_events']} reviews={c['external_outcome_reviews']} "
          f"brief_citations={c['v6_brief_citations_before_gate']} quarantine_appended={rep['quarantine_appended']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
