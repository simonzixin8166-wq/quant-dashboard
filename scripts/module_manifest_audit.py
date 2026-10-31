#!/usr/bin/env python3
"""Read-only module / research-artifact manifest (#133 6116685851 P1-B, 6116717888, 6116804482).

For every docs/research/*.json artifact: producer script, the workflows that run it (and whether any is
scheduled), every reader with file:line, and each reader's ROLE:
  research  forms or prioritises research judgments (shadow research, planner/executor, evidence engines)
  decision  produces owner-facing action states (server action, gold/DCA reminders, playbook state)
  learning  scores, attributes or turns outcomes into memory / policy
  monitor   health, coverage, QA, contracts, counts, leak/boundary guards — reading is NOT learning
  display   browser page only
Roles are assigned per reader script in ROLES below, each with a reason, after reading the code; they are
not inferred from grep counts. A reader that is the artifact's own producer (previous-run state) is excluded.

Derived flags per artifact:
  no_consumer              nobody reads it except monitors/its producer
  monitor_or_display_only  read, but never by research/decision/learning code
  outcome_without_research learning/outcome artifact that never reaches a research or decision producer
                           (graph reachability: artifact → reader → reader's outputs → … → research/decision)
Also reports: Genuine Forward (fo-1.0) vs Auto Research Shadow sample sizes and maturity (separate, never
summed); whether automatic research records cite past cases / error attribution; duplicate SEC sources.
No network; nothing outside research/audit/ is written.
Output: research/audit/module_manifest.json and research/audit/MODULE_MANIFEST.md
"""
from __future__ import annotations
import json, re, subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "docs" / "research"
OUT_JSON = ROOT / "research" / "audit" / "module_manifest.json"
OUT_MD = ROOT / "research" / "audit" / "MODULE_MANIFEST.md"

R, D, L, M, V = "research", "decision", "learning", "monitor", "display"
ROLES = {  # reader → (role, reason)
    "daily_skip_gate.py": (M, "skips only a late duplicate US-close Daily when the session is already published and trusted"),
    "daily_research_job.py": (R, "append-only shadow hypotheses, revisits, maturity"),
    "macro_event_watch.py": (V, "H-01/H-02 homepage macro-event reminder artifact (Shadow, no decisions)"),
    "option_chain_snapshot.py": (M, "OFI-A1: closing option-chain/OI archive to the private ledger; public status is aggregate only (no signals)"),
    "brightline_tranche_shadow.py": (R, "R-01/R-B: BrightLine three-tranche Shadow state (used_in_decision=false)"),
    "fundamental_reliability.py": (R, "B2-02: clean fundamentals-outcome reliability context on SEC evidence (used_in_decision=false)"),
    "experience_inputs.py": (R, "B1: situation/error memory as Shadow evidence in auto research (used_in_decision=false)"),
    "autonomous_research_planner.py": (R, "builds the research queue; priorities use method/regime memory and controlled-policy bonuses"),
    "autonomous_research_executor.py": (R, "writes research briefs with support/counter evidence from situation/method/regime memory"),
    "autonomous_research_agent.py": (R, "agent alerts from learning_engine situation memory"),
    "event_evidence_engine.py": (R, "selects symbols from the planner / attribution for news evidence"),
    "official_evidence_engine.py": (R, "selects symbols from the planner / attribution for SEC filings"),
    "v615_auto_thesis_engine.py": (R, "thesis drafts from official + event evidence"),
    "cross_asset_divergence_engine.py": (R, "market-state research from FRED macro"),
    "breadth_intelligence_engine.py": (R, "breadth research state"),
    "turning_point_checklist.py": (V, "TP-01 external-author turning-point observation list (#133 6235323449; validated=false, not a decision input)"),
    "market_temperature.py": (V, "descriptive 0–100 market temperature from breadth + cross-asset (#133 2026-10-17; not a decision input)"),
    "regime_combination_memory.py": (R, "joint cross-asset + breadth state"),
    "options_opportunity_context.py": (R, "ranks option-inspection universe from support/volatility research"),
    "range_intelligence.py": (R, "market-location research from playbook state"),
    "knowledge_contract.py": (R, "M2 shadow research cases"),
    "company_fundamental_memory.py": (R, "SEC fact collection (reads official_evidence for CIKs)"),
    "sec_fundamentals.py": (R, "SEC fact collection for automatic research"),
    "fundamental_outcome_context.py": (R, "fundamental context for thesis drafts"),
    "source_intelligence_engine.py": (R, "external-author evidence → author action signals"),
    "source_reading_memory.py": (R, "structured propositions from sources"),
    "candidate_rule_compiler.py": (R, "compiles source rules into shadow candidates"),
    "v615_rule_registry.py": (R, "rule identities"), "v615_method_attribution.py": (R, "claim semantics"),
    "server_action_engine.py": (D, "owner-facing option action state (fail-closed)"),
    "investment_watch_engine.py": (D, "gold staged-buying + DCA reminders"),
    "playbook_engine.py": (D, "playbook state + silent forward ledger"),
    "forward_observation_engine.py": (L, "fo-1.0 Genuine Forward ledger (scored at maturity)"),
    "macro_outcome_memory.py": (L, "macro regime → outcomes"), "market_state_outcome_scorecards.py": (L, "cross-asset/breadth/regime scorecards"),
    "company_fundamental_outcome_memory.py": (L, "filing events → outcomes"), "event_outcome_memory.py": (L, "news events → outcomes"),
    "support_volatility_outcome_memory.py": (L, "support/GARCH → outcomes"), "options_opportunity_outcome_memory.py": (L, "option triage → outcomes"),
    "playbook_outcome_engine.py": (L, "forward trigger outcomes"), "forward_learning_feedback.py": (L, "outcome aggregates → research feedback"),
    "walk_forward_replay.py": (L, "historical replay (labelled, never Forward)"), "controlled_learning_policy.py": (L, "bounded research-priority deltas"),
    "challenger_experiment_runner.py": (L, "pre-registered challengers"), "method_memory_engine.py": (L, "method-level memory from validated outcomes"),
    "evidence_attribution_engine.py": (L, "failure / evidence attribution"), "source_outcome_validation.py": (L, "author operations → market outcomes"),
    "source_rule_lifecycle.py": (L, "rule ↔ outcome lifecycle"), "self_improvement_engine.py": (L, "shadow policy candidates + promotion gate"),
    "learning_engine_core.py": (L, "situation memory from history"), "local_history_agent.py": (L, "historical journal, matured 60d stats"),
    "event_window_attribution.py": (L, "outcome events ↔ filings/news"), "v615_event_score.py": (L, "EventScore adapter"),
    "v615_observational_events.py": (L, "descriptive author events"), "v615_author_intelligence.py": (L, "author memory"),
    "backtest_assistant_rules.py": (L, "historical event study"), "backtest_trend_pulse.py": (L, "trend pulse walk-forward study"),
    "candidate_forward_observer.py": (L, "candidate forward ledger"), "candidate_rule_replay.py": (L, "candidate replay"),
    "candidate_rule_families.py": (L, "candidate families"), "candidate_family_scorecard.py": (L, "family scorecards"),
    "candidate_evidence_promotion.py": (L, "candidate evidence gate"), "candidate_event_score.py": (L, "candidate EventScore"),
    "candidate_parameter_queue.py": (L, "unresolved parameter queue"), "evidence_archive.py": (L, "append-only evidence archive"),
    "system_status_center.py": (M, "health snapshot"), "data_learning_coverage_audit.py": (M, "coverage audit (counts)"),
    "generate_build_manifest.py": (M, "build fingerprint"), "autonomous_intelligence_status.py": (M, "roadmap progress report"),
    "private_guardrail.py": (M, "public leak guard"), "learning_funnel_contract.py": (M, "funnel counts"),
    "autonomous_site_qa.mjs": (M, "browser QA"), "research_boundary_guard.py": (M, "dependency/write-boundary guard"),
    "research_program_status.py": (M, "program status"), "playbook_watchdog.py": (M, "playbook freshness watchdog"),
    "operational_incident_memory.py": (M, "ops incident transitions (system learning, not research)"), "daily_guardian.py": (M, "missed-run guard"),
    "source_coverage_audit.py": (M, "source dropout audit"), "source_duplicate_audit.py": (M, "duplicate map"),
    "module_intelligence_engine.py": (M, "declared module graph"), "learning_evaluation_engine.py": (M, "learning scorecard (reports, does not feed research)"),
    "learning_quality_weekly.py": (M, "weekly learning-quality report"), "v615_source_rule_funnel.py": (M, "result-blind funnel"),
    "autonomous_signal_governance.py": (M, "UI contract: may learned research affect actions"), "public_research_evidence_status.py": (V, "presentation adapter"),
    "weekly_research_report.py": (M, "weekly auto-research report"), "auto_research_digest.py": (V, "homepage row digest"),
    "sec_fact_reconcile.py": (M, "SEC reconciliation audit"), "sec_facts_v2.py": (M, "B4-02 unified SEC Shadow fetcher (reads CIKs; no consumer)"), "author_claim_contamination_audit.py": (M, "author-claim gate impact audit + quarantine"), "p1_readiness_audit.py": (M, "B1/B2 readiness quality audit"), "symbol_registry.py": (M, "D-04 universes + missing-history manifest"), "module_manifest_audit.py": (M, "this audit"),
    "v615_forward_intake_health.py": (M, "forward-intake integrity guard (reads validator timestamp only)"),
    "ohlcv_completeness_audit.py": (M, "P0-2 per-symbol OHLCV completeness evidence (read-only audit, no decisions)"),
    "sec_v2_migration_audit.py": (M, "B4-03 pre-migration attribution audit (read-only; no consumer migrated)"),
    "weekly_change_summary.py": (M, "weekly fixed-field change summary; written/sent only on change (ops, no decisions)"),
    "update_fred_macro.py": (R, "FRED/ALFRED macro collector"),
}
PRODUCER_OVERRIDE = {
    "assistant_rule_validation.json": "backtest_assistant_rules.py", "autonomous_agent.json": "autonomous_research_agent.py",
    "challenger_experiments.json": "challenger_experiment_runner.py", "controlled_learning_policy.json": "controlled_learning_policy.py",
    "event_evidence.json": "event_evidence_engine.py", "forward_learning_feedback.json": "forward_learning_feedback.py",
    "official_evidence.json": "official_evidence_engine.py", "self_improvement.json": "self_improvement_engine.py",
    "trend_pulse_backtest.json": "backtest_trend_pulse.py", "auto_research_status.json": "daily_research_job.py",
    "historical_journal.json": "local_history_agent.py", "playbook_status.json": "playbook_engine.py",
    "system_status.json": "system_status_center.py",
    "market_temperature_history.json": "market_temperature.py",  # written via HIST, not an OUT_VARS name
}
OUT_VARS = re.compile(r'^\s*(OUT|OUTPUT|PUBLIC|PUBLIC_OUT|STATUS_OUT|ANCHOR_OUT|AUTHOR_SIGNALS_OUT|HISTORY|STATUS)\s*=\s*(.+)$')
LEARNING_KIND = re.compile(r"(outcome|memory|feedback|replay|scorecard|attribution|validation|lifecycle|self_improvement|challenger|policy|candidate_|backtest|learning_engine|historical_journal)")


def sources():
    out = {}
    for p in sorted(list((ROOT / "scripts").glob("*.py")) + list((ROOT / "scripts").glob("*.mjs")) + list((ROOT / "docs" / "assets").glob("*.js"))):
        out[p] = p.read_text(encoding="utf-8", errors="ignore")
    return out


def workflows():
    wf = {}
    for p in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        t = p.read_text(encoding="utf-8")
        wf[p.name] = {"text": t, "scheduled": bool(re.search(r"^\s*schedule\s*:", t, re.M)) or "- cron:" in t}
    return wf


def last_commit(path):
    try:
        return subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(path)], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
    except Exception:
        return None


def build(now=None, with_git=True):
    now = now or datetime.now(timezone.utc)
    files = sorted(p.name for p in RES.glob("*.json"))
    srcs, wfs = sources(), workflows()
    producers = defaultdict(set)
    for p, s in srcs.items():
        if p.suffix != ".py":
            continue
        for line in s.splitlines():
            m = OUT_VARS.match(line)
            if m:
                for f in files:
                    if f in m.group(2):
                        producers[f].add(p.name)
    for f, prod in PRODUCER_OVERRIDE.items():
        if f in files:
            producers[f] = {prod}
    outputs = defaultdict(set)  # script → artifacts it produces
    for f, ps in producers.items():
        for p in ps:
            outputs[p].add(f)
    readers = defaultdict(list)  # artifact → [(script, line, role, reason)]
    unknown_roles = set()
    for p, s in srcs.items():
        lines = s.splitlines()
        for f in files:
            if f not in s or p.name in producers.get(f, ()):
                continue
            ln = next((i for i, x in enumerate(lines, 1) if f in x), None)
            role, why = (V, "browser page") if p.parent.name == "assets" else ROLES.get(p.name, (None, None))
            if role is None:
                unknown_roles.add(p.name)
                role, why = "unclassified", "role not yet reviewed"
            readers[f].append({"reader": str(p.relative_to(ROOT)), "line": ln, "role": role, "reason": why})
    # graph reachability: does artifact reach a research/decision producer?
    def reaches_research(f, seen=None):
        seen = seen or set()
        if f in seen:
            return []
        seen.add(f)
        hits = []
        for r in readers.get(f, []):
            name = Path(r["reader"]).name
            if r["role"] in (R, D):
                hits.append(name)
            if r["role"] == L:  # follow learning transforms only; research→research hops are data selection, not learning content
                for g in outputs.get(name, ()):
                    hits.extend(reaches_research(g, seen))
        return sorted(set(hits))
    script_wf = {}
    for name in {p for ps in producers.values() for p in ps}:
        hit = [w for w, x in wfs.items() if name in x["text"]]
        script_wf[name] = {"workflows": hit, "scheduled": any(wfs[w]["scheduled"] for w in hit)}
    artifacts = []
    frz = frozen()
    for f in files:
        rs = readers.get(f, [])
        prod = sorted(producers.get(f, []))
        roles = defaultdict(list)
        for r in rs:
            roles[r["role"]].append(f"{r['reader']}:{r['line']}")
        prod_roles = {ROLES.get(p, (None,))[0] for p in prod}
        kind = ("owner_facing_output" if prod_roles & {D, V} else
                "learning_or_outcome" if LEARNING_KIND.search(f) else "other")
        reach = reaches_research(f)
        direct = sorted({Path(r["reader"]).name for r in rs if r["role"] in (R, D)})
        flags = []
        if not rs:
            flags.append("no_consumer")
        elif kind != "owner_facing_output" and not (roles.get(R) or roles.get(D) or roles.get(L)):
            flags.append("monitor_or_display_only")
        if kind == "learning_or_outcome" and not reach:
            flags.append("outcome_without_research")
        if not prod:
            flags.append("no_producer_found")
        if f in frz["artifacts"]:
            flags.append("frozen")  # M-03: skipped in reviews; still produced and kept
        sched = any(script_wf.get(p, {}).get("scheduled") for p in prod)
        if prod and not sched:
            flags.append("producer_not_scheduled")
        artifacts.append({"artifact": f"docs/research/{f}", "kind": kind, "producers": prod,
                          "producer_workflows": sorted({w for p in prod for w in script_wf.get(p, {}).get("workflows", [])}),
                          "producer_scheduled": sched,
                          "consumers": {k: v for k, v in sorted(roles.items())},
                          "direct_research_or_decision_consumers": direct, "reaches_research_or_decision": reach, "flags": flags,
                          "last_commit": last_commit(RES / f) if with_git else None})
    return {"generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "method": "roles assigned per reader script after code review (ROLES); producer self-reads excluded; reachability = direct research/decision readers plus paths through learning transforms only (research→research hops are data selection, not learning content); monitor and display reads never count as learning",
            "artifacts": artifacts, "unclassified_readers": sorted(unknown_roles),
            "summary": summarize(artifacts), "frozen_modules": frz, "tracks": tracks(), "experience_citation": experience_citation(),
            "duplicates": duplicates(), "read_only": True, "production_use": False, "learning_state": "UNPROVEN"}


FROZEN = ROOT / "research" / "registry" / "frozen_modules.json"


def frozen():
    """M-03: frozen artifacts (skipped in reviews, never deleted) and whether the unfreeze condition is met."""
    try:
        reg = json.loads(FROZEN.read_text(encoding="utf-8"))
    except Exception:
        return {"artifacts": [], "unfreeze_due": False}
    fwd = {}
    try:
        fwd = json.loads((RES / "candidate_forward_status.json").read_text(encoding="utf-8")).get("counts") or {}
    except Exception:
        pass
    return {"artifacts": sorted(m["artifact"] for m in reg.get("modules") or []), "frozen_at": reg.get("frozen_at"),
            "unfreeze_due": int(fwd.get("eligible_candidates") or 0) > 0, "unfreeze_when": reg.get("unfreeze_when")}


def summarize(arts):
    f = lambda flag: sorted(a["artifact"].split("/")[-1] for a in arts if flag in a["flags"])
    lo = [a for a in arts if a["kind"] == "learning_or_outcome"]
    return {"artifacts": len(arts), "learning_or_outcome": len(lo),
            "learning_reaching_research": sum(1 for a in lo if a["reaches_research_or_decision"]),
            "no_consumer": f("no_consumer"), "monitor_or_display_only": f("monitor_or_display_only"),
            "outcome_without_research": f("outcome_without_research"), "producer_not_scheduled": f("producer_not_scheduled"),
            "no_producer_found": f("no_producer_found"),
            "frozen": f("frozen"),
            "outcome_without_research_excluding_frozen": sorted(set(f("outcome_without_research")) - set(f("frozen")))}


def _jsonl(p):
    p = ROOT / p
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def tracks():
    g = _jsonl("research/archive/forward_observations.jsonl")
    pr = _jsonl("research/archive/forward_observations_promoted.jsonl")
    sh = [r for r in _jsonl("research/knowledge/auto_research_journal.jsonl") if r.get("type") == "hypothesis"]
    mat = lambda rows, key: min((str(r.get(key)) for r in rows if r.get(key)), default=None)
    def m20(r):
        m = r.get("matures")
        return m.get("20") if isinstance(m, dict) else m
    return {
        "genuine_forward_fo10": {"ledger": "research/archive/forward_observations.jsonl", "observations": len(g),
                                 "sessions": sorted({r.get("session") for r in g}),
                                 "earliest_20_session_maturity": min((str(m20(r)) for r in g if m20(r)), default=None)},
        "promoted_forward_separate_group": {"ledger": "research/archive/forward_observations_promoted.jsonl", "observations": len(pr),
                                            "sessions": sorted({r.get("session") for r in pr}),
                                            "earliest_20_session_maturity": min((str(m20(r)) for r in pr if m20(r)), default=None),
                                            "note": "owner-approved promotions (forward_promotions.jsonl); reported as its own stats group"},
        "auto_research_shadow": {"journal": "research/knowledge/auto_research_journal.jsonl", "hypothesis_records": len(sh),
                                 "distinct_symbol_sessions": len({(r["symbol"], r["market_as_of"]) for r in sh}),
                                 "earliest_maturity": min(((r.get("outcome") or {}).get("matures") or "" for r in sh), default=None) or None,
                                 "forward_eligible": False},
        "rule": "three groups are never summed; shadow is research, not Genuine Forward",
    }


def experience_citation():
    sh = [r for r in _jsonl("research/knowledge/auto_research_journal.jsonl") if r.get("type") == "hypothesis"]
    keys = ("past_cases", "similar_cases", "situation_memory", "method_memory", "error_attribution", "outcome_memory", "precedents")
    cites = [r["record_id"] for r in sh if any(r.get(k) for k in keys)]
    src = (ROOT / "scripts" / "daily_research_job.py").read_text(encoding="utf-8")
    reads_memory = [k for k in ("method_memory", "learning_engine", "evidence_attribution", "regime_combination_memory",
                                "market_state_outcome_scorecards", "macro_outcome_memory", "research_execution") if k in src]
    # B1/B2 (#133 6185390674): does a research OUTPUT (not only an audit) surface the stored experience?
    dsrc = (ROOT / "scripts" / "auto_research_digest.py").read_text(encoding="utf-8")
    dig = ROOT / "docs" / "research" / "auto_research_digest.json"
    try:
        dj = json.loads(dig.read_text(encoding="utf-8"))
    except Exception:
        dj = {}
    surfaced = [i for i in dj.get("items") or [] if isinstance(i.get("experience_basis"), dict)]
    output = {"consumer": "scripts/auto_research_digest.py → docs/research/auto_research_digest.json items[].experience_basis (homepage research row detail)",
              "code_reads_experience": "experience_basis" in dsrc,
              "digest_generated_at": dj.get("generated_at"),
              "digest_items_with_basis": len(surfaced),
              "digest_items_status_used": sum(1 for i in surfaced if i["experience_basis"].get("status") == "used"),
              "status": ("research_output_consumer" if surfaced else "code_wired_awaiting_production_digest") if "experience_basis" in dsrc else "audit_only",
              "used_in_decision": False}
    return {"auto_research_records": len(sh), "records_citing_past_cases": len(cites),
            "daily_research_job_reads_memory_artifacts": reads_memory,
            "research_output": output,
            "status": "wired" if cites else "not yet wired",
            "note": "the V6 planner/executor (research_execution.json) does use situation/method/regime memory for priorities and briefs, "
                    "but those briefs are not the append-only, revisited, maturity-scored automatic research journal; the two are not connected"}


def duplicates():
    rec = ROOT / "research" / "audit" / "sec_fact_reconciliation.json"
    d = json.loads(rec.read_text(encoding="utf-8")) if rec.exists() else {}
    return {"sec_companyfacts": {"sources": ["docs/research/company_fundamental_memory.json", "docs/research/sec_fundamentals.json"],
                                 "overlap_agreement": d.get("overlap_agreement"), "coverage": d.get("coverage"),
                                 "evidence": "research/audit/sec_fact_reconciliation.json (PR #203)"},
            "research_judgment_streams": {"streams": ["docs/research/research_execution.json (V6 executor briefs)",
                                                      "research/knowledge/auto_research_journal.jsonl (automatic shadow research)"],
                                          "issue": "two research-judgment streams; only the executor uses memory, only the journal is revisited and maturity-scored"}}


def markdown(rep):
    s = rep["summary"]; t = rep["tracks"]; e = rep["experience_citation"]
    lines = [f"# MyAlpha module manifest (read-only) — {rep['generated_at']}", "",
             f"Method: {rep['method']}.", "",
             f"- Artifacts: **{s['artifacts']}**; learning/outcome artifacts: **{s['learning_or_outcome']}**, of which reach a research/decision producer: **{s['learning_reaching_research']}**",
             f"- Outcome/learning artifacts that never reach research or decision ({len(s['outcome_without_research'])}): {', '.join(s['outcome_without_research']) or '—'}",
             f"- Read only by monitors/pages ({len(s['monitor_or_display_only'])}): {', '.join(s['monitor_or_display_only']) or '—'}",
             f"- No consumer ({len(s['no_consumer'])}): {', '.join(s['no_consumer']) or '—'}",
             f"- Producer not in any scheduled workflow ({len(s['producer_not_scheduled'])}): {', '.join(s['producer_not_scheduled']) or '—'}",
             f"- Unclassified readers: {', '.join(rep['unclassified_readers']) or 'none'}", "",
             "## Tracks (never summed)", "",
             f"- Genuine Forward fo-1.0: {t['genuine_forward_fo10']['observations']} observations, sessions {', '.join(t['genuine_forward_fo10']['sessions'])}, earliest 20-session maturity {t['genuine_forward_fo10']['earliest_20_session_maturity']}",
             f"- Promoted forward (separate group): {t['promoted_forward_separate_group']['observations']} observations over {len(t['promoted_forward_separate_group']['sessions'])} sessions, earliest maturity {t['promoted_forward_separate_group']['earliest_20_session_maturity']}",
             f"- Auto Research Shadow: {t['auto_research_shadow']['hypothesis_records']} hypothesis records ({t['auto_research_shadow']['distinct_symbol_sessions']} symbol-sessions), earliest maturity {t['auto_research_shadow']['earliest_maturity']}, forward_eligible=false", "",
             "## Does new research cite past experience?", "",
             f"**{e['status']}** — {e['records_citing_past_cases']}/{e['auto_research_records']} automatic research records cite a past case; daily_research_job reads memory artifacts: {e['daily_research_job_reads_memory_artifacts'] or 'none'}. {e['note']}." f"Research output consumer: **{e['research_output']['status']}** ({e['research_output']['digest_items_with_basis']} digest items carry experience_basis, {e['research_output']['digest_items_status_used']} with status used; used_in_decision=false).", "",
             "## Artifacts", "", "| artifact | producer (scheduled) | research / decision | learning | monitor / display | reaches research | flags |", "|---|---|---|---|---|---|---|"]
    for a in rep["artifacts"]:
        c = a["consumers"]
        cell = lambda *ks: "<br>".join(x for k in ks for x in c.get(k, [])) or "—"
        lines.append(f"| {a['artifact'].split('/')[-1]} | {', '.join(a['producers']) or '—'} ({'yes' if a['producer_scheduled'] else 'no'}) | {cell(R, D)} | {cell(L)} | "
                     f"{len(c.get(M, []))} monitor / {len(c.get(V, []))} page | {', '.join(a['reaches_research_or_decision']) or '—'} | {', '.join(a['flags']) or '—'} |")
    return "\n".join(lines) + "\n"


def main():
    rep = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    OUT_MD.write_text(markdown(rep), encoding="utf-8")
    s = rep["summary"]
    print(f"::notice title=Module manifest::artifacts={s['artifacts']} learning/outcome={s['learning_or_outcome']} reaching research={s['learning_reaching_research']} "
          f"outcome_without_research={len(s['outcome_without_research'])} monitor_only={len(s['monitor_or_display_only'])} experience_citation={rep['experience_citation']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
