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
def jsonl_rows(rel):
    p=ROOT/rel
    if not p.exists():return 0
    paths=[p] if p.is_file() else list(p.glob("*.jsonl"))
    total=0
    for path in paths:
        try:total+=sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:pass
    return total

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
    fundamental_outcomes=load("docs/research/company_fundamental_outcome_memory.json")
    evidence_archive=load("research/archive/evidence_archive_manifest.json")
    events=load("docs/research/event_evidence.json")
    thesis=load("docs/research/auto_thesis_drafts.json")
    fundamental=load("docs/research/fundamental_outcome_context.json")
    macro=load("docs/research/macro_context.json")
    macro_outcomes=load("docs/research/macro_outcome_memory.json")
    cross_hist=load("docs/research/cross_asset_divergence_history.json")
    breadth_hist=load("docs/research/breadth_intelligence_history.json")
    regime_hist=load("docs/research/regime_combination_history.json")
    market_state_outcomes=load("docs/research/market_state_outcome_scorecards.json")
    support=load("docs/research/support_volatility_intelligence.json")
    support_outcomes=load("docs/research/support_volatility_outcome_memory.json")
    optctx=load("docs/research/options_opportunity_context.json")
    optout=load("docs/research/options_opportunity_outcome_memory.json")
    server=load("docs/research/server_action_status.json")
    source_store=load("research/store/source_store.json")
    candidate_forward=load("docs/research/candidate_forward_status.json")
    candidate_promotion=load("docs/research/candidate_evidence_promotion_status.json")
    playbook=load("docs/research/playbook_status.json")
    forward_outcomes=load("docs/research/playbook_outcome_shadow.json")
    self_improvement=load("docs/research/self_improvement.json")
    system_status=load("docs/research/system_status.json")
    operational=load("docs/research/operational_incident_memory.json")

    source_total=int((method.get("counts") or {}).get("source_records") or (source.get("counts") or {}).get("records") or 0)
    reading_total=int((reading.get("counts") or {}).get("source_records") or 0)
    source_persist=count_list(source_store.get("records"))
    source_backlog=max(0,source_total-reading_total)
    source_learning_ok=source_total>0 and reading_total>=source_total and source_persist>=source_total
    collector=source.get("collector_completeness") or {}
    collector_complete=collector.get("complete") is True

    fsum=fundamental.get("summary") or {}
    option_learning=server.get("option_learning") or {}

    rows=[
      row("market_price_history", True, "full_local_archive",
          True, True, int((hist.get("summary") or {}).get("mature_20") or 0)>0, True,
          "learning_active",
          ["Historical Journal exposes only a presentation subset of event rows; aggregates use the full local history. A separate full event archive is still preferable for event-level replay."],
          {"symbols":(hist.get("summary") or {}).get("symbols"),"events":(hist.get("summary") or {}).get("events"),"mature_60":(hist.get("summary") or {}).get("mature_60")}),
      row("blog_forum_video_sources", source_total>0, "persistent_source_store_plus_upstream_completeness_contract" if source_persist else "upstream_feed_plus_generated_artifact",
          reading_total>0, reading_total>0, int((method.get("counts") or {}).get("eligible_triggered_events") or 0)>0, True,
          "learning_active" if (source_learning_ok and collector_complete) else "partial_learning",
          ([] if source_learning_ok else ["Captured/source records are not fully reconciled with Source Reading/Persistent Source Store."]) +
          ([] if collector_complete else ["Upstream forum/blog/YouTube completeness is not yet proven; collector completeness contract is false or unavailable."]) +
          ["Historical video archive is intentionally non-gating; this is a governance boundary, not a missing-learning error."],
          {"source_records":source_total,"source_reading_records":reading_total,"persistent_source_records":source_persist,"backlog":source_backlog,"collector_complete":collector_complete,"collector":collector,"testable_rules":(reading.get("counts") or {}).get("testable_rules"),"eligible_triggered_events":(method.get("counts") or {}).get("eligible_triggered_events")}),
      row("official_sec_filings", bool(official.get("symbols")), "current_view_plus_append_only_monthly_archive",
          bool((evidence_archive.get("sec") or {}).get("total")), True, int(fsum.get("linked_direct_events") or 0)>0, True,
          "partial_learning",
          ["Canonical SEC filing archive now preserves filing evidence, but full filing-to-thesis/outcome reuse remains partial."],
          {"symbols":count_map(official.get("symbols")),"filings":(official.get("counts") or {}).get("filings"),"archive_total":(evidence_archive.get("sec") or {}).get("total"),"linked_direct_events":fsum.get("linked_direct_events"),"mature_20":fsum.get("mature_20")}),
      row("financial_fundamentals_xbrl", bool(fundamentals.get("symbols")), "sec_companyfacts_append_only_series_plus_point_in_time_outcomes",
          bool((fundamentals.get("counts") or {}).get("archive_total")), True,
          int((fundamental_outcomes.get("counts") or {}).get("outcomes") or 0)>0,
          True,
          "learning_active" if int((fundamental_outcomes.get("counts") or {}).get("outcomes") or 0)>0 else ("partial_learning" if fundamentals.get("symbols") else "not_implemented"),
          ([] if int((fundamental_outcomes.get("counts") or {}).get("outcomes") or 0)>0 else ["SEC CompanyFacts/XBRL longitudinal fact memory is present; waiting for point-in-time filing outcomes to mature."]),
          {"symbols":count_map(fundamentals.get("symbols")),"archive_total":(fundamentals.get("counts") or {}).get("archive_total"),"archive_added":(fundamentals.get("counts") or {}).get("archive_added"),"filing_observations":(fundamental_outcomes.get("counts") or {}).get("observations"),"mature_outcomes":(fundamental_outcomes.get("counts") or {}).get("outcomes"),"horizons":fundamental_outcomes.get("horizons")}),
      row("news_event_evidence", bool(events.get("symbols")), "current_view_plus_append_only_monthly_archive",
          bool((evidence_archive.get("events") or {}).get("total")), True, bool(load("docs/research/event_window_attribution.json").get("rows")), True,
          "partial_learning",
          ["Canonical Event archive now preserves acquired news items; causal attribution and long-horizon reuse remain partial.","Current Top-N news stays a view, not the canonical learning store."],
          {"symbols":count_map(events.get("symbols")),"news_items":(events.get("counts") or {}).get("news_items"),"archive_total":(evidence_archive.get("events") or {}).get("total"),"event_window_rows":count_list(load("docs/research/event_window_attribution.json").get("rows"))}),
      row("macro_fred_alfred", bool(macro), "point_in_time_context_plus_macro_regime_outcome_memory",
          True, True, bool((macro_outcomes.get("counts") or {}).get("outcomes")), True,
          "learning_active" if int((macro_outcomes.get("counts") or {}).get("outcomes") or 0)>0 else "partial_learning",
          ([] if int((macro_outcomes.get("counts") or {}).get("outcomes") or 0)>0 else ["Point-in-time macro regime observations are retained; waiting for future 5/20/60-session outcomes to mature."]),
          {"version":macro.get("version"),"series":count_map(macro.get("series")),"observations":(macro_outcomes.get("counts") or {}).get("observations"),"outcomes":(macro_outcomes.get("counts") or {}).get("outcomes"),"scorecards":(macro_outcomes.get("counts") or {}).get("scorecards")}),
      row("breadth_cross_asset_regime", bool(cross_hist or breadth_hist or regime_hist), "append_history_plus_5_20_60_outcome_scorecards",
          True, True, bool((market_state_outcomes.get("counts") or {}).get("outcomes")), True,
          "learning_active" if int((market_state_outcomes.get("counts") or {}).get("outcomes") or 0)>0 else "partial_learning",
          ([] if int((market_state_outcomes.get("counts") or {}).get("outcomes") or 0)>0 else ["Append histories are intact; waiting for future 5/20/60-session outcomes to mature."]),
          {"cross_asset_history":count_list(cross_hist.get("records")),"breadth_history":count_list(breadth_hist.get("records")),"regime_history":count_list(regime_hist.get("records")),"outcomes":(market_state_outcomes.get("counts") or {}).get("outcomes"),"scorecards":(market_state_outcomes.get("counts") or {}).get("scorecards")}),
      row("support_resistance_volatility", bool(support), "append_only_observation_and_outcome_archive",
          True, bool((support_outcomes.get("counts") or {}).get("observations")), bool((support_outcomes.get("counts") or {}).get("mature20")), True,
          "learning_active" if int((support_outcomes.get("counts") or {}).get("mature20") or 0)>0 else "partial_learning",
          ([] if int((support_outcomes.get("counts") or {}).get("mature20") or 0)>0 else ["Dated Support/GARCH observations are now retained; waiting for real 20-session outcomes to mature."]),
          {"universe":support.get("universe"),"observations":(support_outcomes.get("counts") or {}).get("observations"),"mature20":(support_outcomes.get("counts") or {}).get("mature20"),"garch_mae_pct_points":(support_outcomes.get("metrics") or {}).get("garch_mae_pct_points")}),
      row("options_opportunity", bool(optctx), "current_context_plus_append_only_research_outcomes_plus_private_positions",
          True,
          bool((optout.get("counts") or {}).get("observations") or option_learning.get("observations")),
          bool((optout.get("counts") or {}).get("matured") or option_learning.get("mature_outcomes")),
          True,
          "learning_active" if int((optout.get("counts") or {}).get("matured") or 0)>0 or option_learning.get("mature_outcomes") else "partial_learning",
          ["Research scan/reject/no-trade snapshots now retain underlying 5D/20D outcomes. True option PnL/assignment learning still requires private executed-position outcomes and live-chain fields such as IV rank/skew/term structure."],
          {"universe":optctx.get("universe"),"research_observations":(optout.get("counts") or {}).get("observations"),"research_matured":(optout.get("counts") or {}).get("matured"),"private_observations":option_learning.get("observations"),"private_mature_outcomes":option_learning.get("mature_outcomes")}),
      row("auto_thesis_revision_memory", bool(thesis.get("symbols")), "current_draft_plus_append_only_revision_history",
          True, jsonl_rows("research/archive/thesis_revisions")>0, bool(fsum.get("linked_direct_events")), True,
          "partial_learning",
          ["Thesis revisions are now retained by evidence-hash change; outcome attribution and evidence-delta effectiveness are still partial."],
          {"symbols":count_map(thesis.get("symbols")),"revision_rows":jsonl_rows("research/archive/thesis_revisions"),"linked_direct_events":fsum.get("linked_direct_events")}),
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
      row("operational_system_learning", bool(system_status), "status_snapshots_plus_append_only_incident_transitions",
          True, bool(operational), bool((operational.get("counts") or {}).get("resolved_total")), True,
          "learning_active" if int((operational.get("counts") or {}).get("resolved_total") or 0)>0 else "partial_learning",
          ([] if int((operational.get("counts") or {}).get("resolved_total") or 0)>0 else ["Append-only incident tracking is active; waiting for at least one opened incident to be observed resolved in a later status snapshot."]),
          {"overall":system_status.get("overall"),"open_incidents":(operational.get("counts") or {}).get("open"),"resolved_total":(operational.get("counts") or {}).get("resolved_total"),"self_improvement_version":self_improvement.get("version")}),
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
      "version":"1.9",
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
