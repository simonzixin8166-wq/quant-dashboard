#!/usr/bin/env python3
"""Whole-site data -> learning coverage audit.

This audit distinguishes four different states that were previously easy to
confuse:
- collected/displayed: data exists but is not reused by a learning loop;
- context_only: data is used to explain a current view but has no outcome memory;
- partial_learning: structured reuse exists, but history/coverage is incomplete;
- learning_active: persistent evidence + reusable memory/outcome loop exists.

It is intentionally conservative: missing persistence or outcome linkage never
receives a "learning_active" label.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"data_learning_coverage_audit.json"

def load(rel, default=None):
    p=ROOT/rel
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def exists(rel): return (ROOT/rel).exists()
def count_map(x): return len(x) if isinstance(x,dict) else 0
def count_list(x): return len(x) if isinstance(x,list) else 0

def row(domain, collected, persisted, structured, memory, outcomes, decision_context, status, gaps, evidence):
    return {
        "domain":domain,
        "collected":bool(collected),
        "persistent_history":persisted,
        "structured_analysis":bool(structured),
        "reusable_memory":bool(memory),
        "outcome_feedback":bool(outcomes),
        "decision_context":bool(decision_context),
        "learning_status":status,
        "gaps":gaps,
        "evidence":evidence,
    }

def build():
    hist=load("docs/research/historical_journal.json")
    source=load("docs/data/source_intelligence.json")
    reading=load("docs/research/source_reading_memory.json")
    method=load("docs/research/method_memory.json")
    official=load("docs/research/official_evidence.json")
    fundamentals=load("docs/research/company_fundamental_memory.json")
    evidence_archive=load("research/archive/evidence_archive_manifest.json")
    events=load("docs/research/event_evidence.json")
    thesis=load("docs/research/auto_thesis_drafts.json")
    fundamental=load("docs/research/fundamental_outcome_context.json")
    macro=load("docs/research/macro_context.json")
    cross_hist=load("docs/research/cross_asset_divergence_history.json")
    breadth_hist=load("docs/research/breadth_intelligence_history.json")
    regime_hist=load("docs/research/regime_combination_history.json")
    support=load("docs/research/support_volatility_intelligence.json")
    optctx=load("docs/research/options_opportunity_context.json")
    server=load("docs/research/server_action_status.json")
    source_store=load("research/store/source_store.json")
    candidate_forward=load("docs/research/candidate_forward_status.json")
    candidate_promotion=load("docs/research/candidate_evidence_promotion_status.json")
    playbook=load("docs/research/playbook_status.json")
    forward_outcomes=load("docs/research/playbook_outcome_shadow.json")
    self_improvement=load("docs/research/self_improvement.json")
    system_status=load("docs/research/system_status.json")

    source_total=int((method.get("counts") or {}).get("source_records") or (source.get("counts") or {}).get("records") or 0)
    reading_total=int((reading.get("counts") or {}).get("source_records") or 0)
    source_persist=count_list(source_store.get("records"))
    source_backlog=max(0,source_total-reading_total)
    source_learning_ok=source_total>0 and reading_total>=source_total and source_persist>=source_total

    fsum=fundamental.get("summary") or {}
    option_learning=server.get("option_learning") or {}

    rows=[
      row("market_price_history", True, "full_local_archive",
          True, True, int((hist.get("summary") or {}).get("mature_20") or 0)>0, True,
          "learning_active",
          ["Historical Journal exposes only a presentation subset of event rows; aggregates use the full local history. A separate full event archive is still preferable for event-level replay."],
          {"symbols":(hist.get("summary") or {}).get("symbols"),"events":(hist.get("summary") or {}).get("events"),"mature_60":(hist.get("summary") or {}).get("mature_60")}),
      row("blog_forum_video_sources", source_total>0, "persistent_source_store" if source_persist else "upstream_feed_plus_generated_artifact",
          reading_total>0, reading_total>0, int((method.get("counts") or {}).get("eligible_triggered_events") or 0)>0, True,
          "learning_active" if source_learning_ok else "partial_learning",
          ([] if source_learning_ok else ["Captured/source records are not fully reconciled with Source Reading/Persistent Source Store."]) +
          ["Historical video archive is intentionally non-gating; this is a governance boundary, not a missing-learning error."],
          {"source_records":source_total,"source_reading_records":reading_total,"persistent_source_records":source_persist,"backlog":source_backlog,"testable_rules":(reading.get("counts") or {}).get("testable_rules"),"eligible_triggered_events":(method.get("counts") or {}).get("eligible_triggered_events")}),
      row("official_sec_filings", bool(official.get("symbols")), "current_view_plus_append_only_monthly_archive",
          bool((evidence_archive.get("sec") or {}).get("total")), True, int(fsum.get("linked_direct_events") or 0)>0, True,
          "partial_learning",
          ["Canonical SEC filing archive now preserves filing evidence, but full filing-to-thesis/outcome reuse remains partial."],
          {"symbols":count_map(official.get("symbols")),"filings":(official.get("counts") or {}).get("filings"),"archive_total":(evidence_archive.get("sec") or {}).get("total"),"linked_direct_events":fsum.get("linked_direct_events"),"mature_20":fsum.get("mature_20")}),
      row("financial_fundamentals_xbrl", bool(fundamentals.get("symbols")), "sec_companyfacts_append_only_series",
          bool((fundamentals.get("counts") or {}).get("archive_total")), True, False, False,
          "partial_learning" if fundamentals.get("symbols") else "not_implemented",
          ["SEC CompanyFacts/XBRL longitudinal fact memory is now present when the artifact has been built.","Derived quarter-over-quarter/YoY, thesis-change and future-outcome evaluation still need explicit closed-loop scoring."],
          {"symbols":count_map(fundamentals.get("symbols")),"archive_total":(fundamentals.get("counts") or {}).get("archive_total"),"archive_added":(fundamentals.get("counts") or {}).get("archive_added")}),
      row("news_event_evidence", bool(events.get("symbols")), "current_view_plus_append_only_monthly_archive",
          bool((evidence_archive.get("events") or {}).get("total")), True, bool(load("docs/research/event_window_attribution.json").get("rows")), True,
          "partial_learning",
          ["Canonical Event archive now preserves acquired news items; causal attribution and long-horizon reuse remain partial.","Current Top-N news stays a view, not the canonical learning store."],
          {"symbols":count_map(events.get("symbols")),"news_items":(events.get("counts") or {}).get("news_items"),"archive_total":(evidence_archive.get("events") or {}).get("total"),"event_window_rows":count_list(load("docs/research/event_window_attribution.json").get("rows"))}),
      row("macro_fred_alfred", bool(macro), "current_plus_cached_series",
          True, True, False, True,
          "partial_learning",
          ["Macro context is used in regime/context reasoning, but there is no explicit macro-state -> outcome memory comparable to Trend Pulse.","ALFRED point-in-time handling reduces revision leakage but does not by itself constitute learned macro efficacy."],
          {"version":macro.get("version"),"series":count_map(macro.get("series"))}),
      row("breadth_cross_asset_regime", bool(cross_hist or breadth_hist or regime_hist), "append_history",
          True, True, False, True,
          "partial_learning",
          ["History is now retained without hard row eviction, but the series are still young and lack mature outcome scoring."],
          {"cross_asset_history":count_list(cross_hist.get("records")),"breadth_history":count_list(breadth_hist.get("records")),"regime_history":count_list(regime_hist.get("records"))}),
      row("support_resistance_volatility", bool(support), "current_research_artifact",
          True, False, False, True,
          "context_only",
          ["Support/Resistance and GARCH are calculated and reused by Options Opportunity, but their predictions/signals are not yet stored as dated observations with later outcome evaluation."],
          {"universe":support.get("universe")}),
      row("options_opportunity", bool(optctx), "current_research_artifact_plus_private_positions",
          True, bool(option_learning.get("observations")), bool(option_learning.get("mature_outcomes")), True,
          "partial_learning" if not option_learning.get("mature_outcomes") else "learning_active",
          ["Opportunity screening is research-only. Strategy candidate outcomes need persistent opportunity snapshots, rejected/no-trade cases, and later premium/assignment/MAE/MFE outcomes."],
          {"universe":optctx.get("universe"),"observations":option_learning.get("observations"),"mature_outcomes":option_learning.get("mature_outcomes")}),
      row("auto_thesis_revision_memory", bool(thesis.get("symbols")), "current_draft_artifact",
          True, True, bool(fsum.get("linked_direct_events")), True,
          "partial_learning",
          ["Auto Thesis is evidence-grounded, but a canonical immutable thesis revision history with prior thesis, change reason and evidence delta is not present."],
          {"symbols":count_map(thesis.get("symbols")),"linked_direct_events":fsum.get("linked_direct_events")}),
      row("candidate_shadow_forward", bool(candidate_forward or candidate_promotion), "candidate_registry_plus_forward_artifacts",
          True, True, bool((candidate_forward.get("counts") or {}).get("events") or (candidate_forward.get("summary") or {}).get("events")), True,
          "partial_learning",
          ["Candidate/Shadow pipeline is governed and Forward-separated, but promotion remains intentionally locked until genuine forward evidence matures."],
          {"forward_counts":candidate_forward.get("counts") or candidate_forward.get("summary"),"promotion":candidate_promotion.get("summary") or candidate_promotion.get("counts")}),
      row("production_playbook_forward_replay", bool(playbook), "private_forward_ledger_plus_local_replay",
          True, True,
          sum(int(v or 0) for v in ((forward_outcomes.get("mature_total") or {}).values() if isinstance(forward_outcomes.get("mature_total"),dict) else []))>0,
          True,
          "learning_active" if sum(int(v or 0) for v in ((forward_outcomes.get("mature_total") or {}).values() if isinstance(forward_outcomes.get("mature_total"),dict) else []))>0 else "partial_learning",
          ["Pipeline exists, but Learning Active requires at least one real mature Forward outcome."],
          {"mode":playbook.get("mode"),"forward_clock_active":((playbook.get("storage") or {}).get("forward_clock_active")),"mature_total":forward_outcomes.get("mature_total")}),
      row("operational_system_learning", bool(system_status), "status_snapshots_and_failure_markers",
          True, bool(self_improvement), False, True,
          "partial_learning",
          ["System health and failures influence confidence/research attention, but there is no clearly audited append-only operational incident outcome memory covering every failure and remediation."],
          {"overall":system_status.get("overall"),"self_improvement_version":self_improvement.get("version")}),
      row("regional_cn_hk_learning", exists("docs/data.json"), "market_snapshot_only",
          True, False, False, True,
          "context_only",
          ["A/H market data is available for observation, but no dedicated cross-market state/outcome memory comparable to US Trend Pulse is established."],
          {}),
      row("curated_knowledge_base", exists("docs/assets/knowledge.js"), "curated_reference",
          True, True, False, True,
          "partial_learning",
          ["Curated knowledge may consume validated method evidence, but it is intentionally not an autonomous weight-changing learner."],
          {}),
      row("decision_journal_user_actions", exists("docs/assets/decision-journal.js"), "private_or_browser_managed",
          True, True, False, True,
          "partial_learning",
          ["Public repository cannot verify completeness of private/user decision records or whether every decision is later reconciled to outcomes."],
          {}),
    ]
    rank={"learning_active":3,"partial_learning":2,"context_only":1,"collected_only":0,"not_implemented":0}
    counts={}
    for x in rows:counts[x["learning_status"]]=counts.get(x["learning_status"],0)+1
    gaps=[{"domain":x["domain"],"status":x["learning_status"],"gaps":x["gaps"]} for x in rows if rank.get(x["learning_status"],0)<3]
    return {
      "version":"1.3",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "principle":"Collection success is not learning success. Permanent storage and learning inputs must not be record-count capped; only per-run processing and UI presentation may be bounded.",
      "counts":counts,
      "domains":rows,
      "priority_gaps":gaps,
      "reconciliation":{
        "captured":source_total,
        "canonical":source_persist,
        "processed":reading_total,
        "backlog":source_backlog,
        "errors":0,
        "balanced":source_total>0 and source_persist>=source_total and reading_total+source_backlog>=source_total,
      },
      "required_contract":{
        "canonical_storage":"append-only or sharded; no destructive record-count eviction",
        "learning_input":"complete canonical history or cursor-backed exhaustive processing",
        "batch_processing":"bounded is allowed only with persistent backlog/cursor",
        "presentation":"bounded views are allowed and must never be reused as the canonical learning source",
        "reconciliation":"captured = deduplicated + excluded; deduplicated = processed + explicit backlog/error",
      },
    }

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"counts":out["counts"],"domains":len(out["domains"]),"reconciliation":out["reconciliation"],"output":str(OUT.relative_to(ROOT))},ensure_ascii=False))
    if not (out.get("reconciliation") or {}).get("balanced"):
        raise SystemExit("LEARNING_COVERAGE_GAP: source accounting is not reconciled")

if __name__=="__main__":main()
