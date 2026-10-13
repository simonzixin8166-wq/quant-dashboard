# MyAlpha module manifest (read-only) — 2026-10-13T04:36:00Z

Method: roles assigned per reader script after code review (ROLES); producer self-reads excluded; reachability = direct research/decision readers plus paths through learning transforms only (research→research hops are data selection, not learning content); monitor and display reads never count as learning.

- Artifacts: **72**; learning/outcome artifacts: **34**, of which reach a research/decision producer: **14**
- Outcome/learning artifacts that never reach research or decision (20): assistant_rule_validation.json, candidate_eventscore_status.json, candidate_evidence_promotion_status.json, candidate_family_scorecard_status.json, candidate_forward_status.json, candidate_parameter_queue.json, candidate_rule_family_status.json, candidate_rule_replay.json, candidate_rule_status.json, challenger_experiments.json, company_fundamental_memory.json, event_outcome_memory.json, fundamental_outcome_context.json, macro_outcome_memory.json, market_state_outcome_scorecards.json, operational_incident_memory.json, options_opportunity_outcome_memory.json, source_rule_lifecycle.json, support_volatility_outcome_memory.json, trend_pulse_backtest.json
- Read only by monitors/pages (29): assistant_rule_validation.json, author_action_signals.json, author_intelligence.json, auto_research_status.json, candidate_eventscore_status.json, candidate_family_scorecard_status.json, candidate_forward_status.json, candidate_parameter_queue.json, candidate_rule_status.json, challenger_experiments.json, company_fundamental_memory.json, data_learning_coverage_audit.json, event_outcome_memory.json, forward_observation_status.json, fundamental_outcome_context.json, learning_evaluation.json, learning_funnel.json, learning_quality_weekly.json, macro_outcome_memory.json, market_state_outcome_scorecards.json, operational_incident_memory.json, options_opportunity_outcome_memory.json, range_intelligence.json, signal_governance.json, source_coverage_audit.json, source_rule_lifecycle.json, support_volatility_outcome_memory.json, trend_pulse_backtest.json, v615_program_status.json
- No consumer (3): autonomous_intelligence_status.json, candidate_rule_family_status.json, weekly_research_report.json
- Producer not in any scheduled workflow (0): —
- Unclassified readers: none

## Tracks (never summed)

- Genuine Forward fo-1.0: 74 observations, sessions 2026-10-08, 2026-10-09, 2026-10-12, earliest 20-session maturity 2026-11-05
- Promoted forward (separate group): 130 observations over 6 sessions, earliest maturity 2026-10-27
- Auto Research Shadow: 79 hypothesis records (29 symbol-sessions), earliest maturity 2026-11-06, forward_eligible=false

## Does new research cite past experience?

**wired** — 8/79 automatic research records cite a past case; daily_research_job reads memory artifacts: ['method_memory', 'learning_engine', 'evidence_attribution']. the V6 planner/executor (research_execution.json) does use situation/method/regime memory for priorities and briefs, but those briefs are not the append-only, revisited, maturity-scored automatic research journal; the two are not connected.

## Artifacts

| artifact | producer (scheduled) | research / decision | learning | monitor / display | reaches research | flags |
|---|---|---|---|---|---|---|
| assistant_rule_validation.json | backtest_assistant_rules.py (yes) | — | — | 2 monitor / 2 page | — | monitor_or_display_only, outcome_without_research |
| author_action_signals.json | source_intelligence_engine.py (yes) | — | — | 0 monitor / 1 page | — | monitor_or_display_only |
| author_intelligence.json | v615_author_intelligence.py (yes) | — | — | 1 monitor / 1 page | — | monitor_or_display_only |
| auto_research_digest.json | auto_research_digest.py (yes) | — | — | 0 monitor / 1 page | — | — |
| auto_research_status.json | daily_research_job.py (yes) | — | — | 2 monitor / 1 page | — | monitor_or_display_only |
| auto_thesis_drafts.json | v615_auto_thesis_engine.py (yes) | scripts/daily_research_job.py:9<br>scripts/fundamental_outcome_context.py:9<br>scripts/knowledge_contract.py:10<br>scripts/server_action_engine.py:20 | — | 3 monitor / 1 page | daily_research_job.py, fundamental_outcome_context.py, knowledge_contract.py, server_action_engine.py | — |
| autonomous_agent.json | autonomous_research_agent.py (yes) | scripts/autonomous_research_planner.py:15 | scripts/evidence_attribution_engine.py:12 | 6 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py, event_evidence_engine.py, official_evidence_engine.py | — |
| autonomous_intelligence_status.json | autonomous_intelligence_status.py (yes) | — | — | 0 monitor / 0 page | — | no_consumer |
| breadth_intelligence.json | breadth_intelligence_engine.py (yes) | scripts/autonomous_research_executor.py:34<br>scripts/autonomous_research_planner.py:24<br>scripts/regime_combination_memory.py:18 | — | 3 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, regime_combination_memory.py | — |
| breadth_intelligence_history.json | breadth_intelligence_engine.py (yes) | scripts/autonomous_research_executor.py:35 | scripts/market_state_outcome_scorecards.py:11<br>scripts/self_improvement_engine.py:20 | 4 monitor / 0 page | autonomous_research_executor.py, autonomous_research_planner.py | — |
| candidate_eventscore_status.json | candidate_event_score.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research, frozen |
| candidate_evidence_promotion_status.json | candidate_evidence_promotion.py (yes) | — | scripts/candidate_event_score.py:201 | 3 monitor / 0 page | — | outcome_without_research, frozen |
| candidate_family_scorecard_status.json | candidate_family_scorecard.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research, frozen |
| candidate_forward_status.json | candidate_forward_observer.py (yes) | — | — | 4 monitor / 0 page | — | monitor_or_display_only, outcome_without_research, frozen |
| candidate_parameter_queue.json | candidate_parameter_queue.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| candidate_rule_family_status.json | candidate_rule_families.py (yes) | — | — | 0 monitor / 0 page | — | no_consumer, outcome_without_research, frozen |
| candidate_rule_replay.json | candidate_rule_replay.py (yes) | — | scripts/candidate_rule_families.py:15 | 1 monitor / 0 page | — | outcome_without_research |
| candidate_rule_status.json | candidate_rule_compiler.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| challenger_experiments.json | challenger_experiment_runner.py (yes) | — | — | 3 monitor / 1 page | — | monitor_or_display_only, outcome_without_research |
| company_fundamental_memory.json | company_fundamental_memory.py (yes) | — | — | 5 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| company_fundamental_outcome_memory.json | company_fundamental_outcome_memory.py (yes) | scripts/fundamental_reliability.py:25 | — | 1 monitor / 0 page | fundamental_reliability.py | — |
| controlled_learning_policy.json | controlled_learning_policy.py (yes) | scripts/autonomous_research_planner.py:27 | — | 5 monitor / 1 page | autonomous_research_planner.py | — |
| cross_asset_divergence.json | cross_asset_divergence_engine.py (yes) | scripts/autonomous_research_executor.py:32<br>scripts/autonomous_research_planner.py:23<br>scripts/regime_combination_memory.py:17 | — | 3 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, regime_combination_memory.py | — |
| cross_asset_divergence_history.json | cross_asset_divergence_engine.py (yes) | scripts/autonomous_research_executor.py:33 | scripts/market_state_outcome_scorecards.py:10<br>scripts/self_improvement_engine.py:19 | 4 monitor / 0 page | autonomous_research_executor.py, autonomous_research_planner.py | — |
| data_learning_coverage_audit.json | data_learning_coverage_audit.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only |
| event_evidence.json | event_evidence_engine.py (yes) | scripts/autonomous_research_executor.py:31<br>scripts/v615_auto_thesis_engine.py:15 | scripts/event_window_attribution.py:19<br>scripts/evidence_archive.py:14 | 7 monitor / 0 page | autonomous_research_executor.py, v615_auto_thesis_engine.py | — |
| event_outcome_memory.json | event_outcome_memory.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| event_window_attribution.json | event_window_attribution.py (yes) | scripts/autonomous_research_executor.py:30 | — | 5 monitor / 0 page | autonomous_research_executor.py | — |
| evidence_attribution.json | evidence_attribution_engine.py (yes) | scripts/autonomous_research_executor.py:24<br>scripts/autonomous_research_planner.py:17<br>scripts/daily_research_job.py:43<br>scripts/event_evidence_engine.py:20<br>scripts/official_evidence_engine.py:20 | scripts/event_window_attribution.py:17<br>scripts/method_memory_engine.py:27<br>scripts/self_improvement_engine.py:14 | 4 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py, event_evidence_engine.py, official_evidence_engine.py | — |
| evidence_status.json | public_research_evidence_status.py (yes) | — | — | 3 monitor / 1 page | — | — |
| forward_learning_feedback.json | forward_learning_feedback.py (yes) | — | scripts/challenger_experiment_runner.py:22<br>scripts/controlled_learning_policy.py:24 | 4 monitor / 1 page | autonomous_research_planner.py | — |
| forward_observation_status.json | forward_observation_engine.py (yes) | — | — | 0 monitor / 1 page | — | monitor_or_display_only |
| fundamental_outcome_context.json | fundamental_outcome_context.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| historical_journal.json | local_history_agent.py (yes) | scripts/playbook_engine.py:21 | scripts/evidence_attribution_engine.py:13<br>scripts/learning_engine_core.py:13 | 6 monitor / 2 page | autonomous_research_agent.py, autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py, event_evidence_engine.py, experience_inputs.py, official_evidence_engine.py, playbook_engine.py | — |
| investment_actions_status.json | investment_watch_engine.py (yes) | — | — | 1 monitor / 1 page | — | — |
| learning_engine.json | learning_engine_core.py (yes) | scripts/autonomous_research_agent.py:12<br>scripts/autonomous_research_executor.py:23<br>scripts/autonomous_research_planner.py:16<br>scripts/daily_research_job.py:42<br>scripts/experience_inputs.py:43 | scripts/evidence_attribution_engine.py:11 | 4 monitor / 0 page | autonomous_research_agent.py, autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py, event_evidence_engine.py, experience_inputs.py, official_evidence_engine.py | — |
| learning_evaluation.json | learning_evaluation_engine.py (yes) | — | — | 3 monitor / 1 page | — | monitor_or_display_only |
| learning_funnel.json | learning_funnel_contract.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only |
| learning_quality_weekly.json | learning_quality_weekly.py (yes) | — | — | 0 monitor / 1 page | — | monitor_or_display_only |
| ledger_anchor.json | playbook_engine.py (yes) | — | — | 3 monitor / 1 page | — | — |
| macro_context.json | update_fred_macro.py (yes) | scripts/cross_asset_divergence_engine.py:16<br>scripts/daily_research_job.py:8 | scripts/learning_engine_core.py:14<br>scripts/macro_outcome_memory.py:10 | 1 monitor / 0 page | autonomous_research_agent.py, autonomous_research_executor.py, autonomous_research_planner.py, cross_asset_divergence_engine.py, daily_research_job.py, event_evidence_engine.py, experience_inputs.py, official_evidence_engine.py | — |
| macro_outcome_memory.json | macro_outcome_memory.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| market_state_outcome_scorecards.json | market_state_outcome_scorecards.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| method_memory.json | method_memory_engine.py (yes) | scripts/autonomous_research_executor.py:25<br>scripts/autonomous_research_planner.py:18<br>scripts/daily_research_job.py:44 | scripts/controlled_learning_policy.py:23<br>scripts/self_improvement_engine.py:15 | 7 monitor / 2 page | autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py | — |
| module_intelligence.json | module_intelligence_engine.py (yes) | scripts/autonomous_research_executor.py:28<br>scripts/autonomous_research_planner.py:22 | scripts/self_improvement_engine.py:17 | 2 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py | — |
| official_evidence.json | official_evidence_engine.py (yes) | scripts/autonomous_research_executor.py:29<br>scripts/company_fundamental_memory.py:13<br>scripts/v615_auto_thesis_engine.py:14 | scripts/event_window_attribution.py:18<br>scripts/evidence_archive.py:13 | 7 monitor / 0 page | autonomous_research_executor.py, company_fundamental_memory.py, v615_auto_thesis_engine.py | — |
| operational_incident_memory.json | operational_incident_memory.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| options_opportunity_context.json | options_opportunity_context.py (yes) | — | scripts/options_opportunity_outcome_memory.py:15 | 4 monitor / 1 page | — | — |
| options_opportunity_outcome_memory.json | options_opportunity_outcome_memory.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| playbook_outcome_shadow.json | playbook_outcome_engine.py (yes) | — | scripts/controlled_learning_policy.py:21<br>scripts/forward_learning_feedback.py:20 | 3 monitor / 1 page | autonomous_research_planner.py | — |
| playbook_status.json | playbook_engine.py (yes) | scripts/range_intelligence.py:19 | scripts/playbook_outcome_engine.py:28 | 5 monitor / 1 page | autonomous_research_planner.py, range_intelligence.py | — |
| range_intelligence.json | range_intelligence.py (yes) | — | — | 2 monitor / 1 page | — | monitor_or_display_only |
| regime_combination_history.json | regime_combination_memory.py (yes) | scripts/autonomous_research_executor.py:37 | scripts/market_state_outcome_scorecards.py:12<br>scripts/self_improvement_engine.py:21 | 4 monitor / 0 page | autonomous_research_executor.py, autonomous_research_planner.py | — |
| regime_combination_memory.json | regime_combination_memory.py (yes) | scripts/autonomous_research_executor.py:36<br>scripts/autonomous_research_planner.py:25 | — | 4 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py | — |
| research_execution.json | autonomous_research_executor.py (yes) | — | scripts/self_improvement_engine.py:18 | 7 monitor / 1 page | autonomous_research_planner.py | — |
| research_planner.json | autonomous_research_planner.py (yes) | scripts/autonomous_research_executor.py:22<br>scripts/event_evidence_engine.py:17<br>scripts/official_evidence_engine.py:18 | scripts/self_improvement_engine.py:16 | 4 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, event_evidence_engine.py, official_evidence_engine.py | — |
| sec_fundamentals.json | sec_fundamentals.py (yes) | scripts/daily_research_job.py:41 | — | 3 monitor / 0 page | daily_research_job.py | — |
| self_improvement.json | self_improvement_engine.py (yes) | — | scripts/controlled_learning_policy.py:22 | 6 monitor / 1 page | autonomous_research_planner.py | — |
| server_action_status.json | server_action_engine.py (yes) | — | — | 6 monitor / 1 page | — | — |
| signal_governance.json | autonomous_signal_governance.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only |
| source_coverage_audit.json | source_coverage_audit.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only |
| source_duplicate_map.json | source_duplicate_audit.py (yes) | scripts/source_reading_memory.py:28 | scripts/method_memory_engine.py:31 | 0 monitor / 0 page | autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py, source_reading_memory.py | — |
| source_outcome_validation.json | source_outcome_validation.py (yes) | — | scripts/evidence_attribution_engine.py:15<br>scripts/method_memory_engine.py:26<br>scripts/source_rule_lifecycle.py:23<br>scripts/v615_event_score.py:17<br>scripts/v615_observational_events.py:15 | 4 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, daily_research_job.py, event_evidence_engine.py, official_evidence_engine.py | — |
| source_reading_memory.json | source_reading_memory.py (yes) | scripts/autonomous_research_executor.py:27<br>scripts/autonomous_research_planner.py:20<br>scripts/candidate_rule_compiler.py:30<br>scripts/v615_method_attribution.py:12<br>scripts/v615_rule_registry.py:14 | scripts/method_memory_engine.py:28<br>scripts/source_rule_lifecycle.py:22 | 6 monitor / 1 page | autonomous_research_executor.py, autonomous_research_planner.py, candidate_rule_compiler.py, daily_research_job.py, v615_method_attribution.py, v615_rule_registry.py | — |
| source_rule_lifecycle.json | source_rule_lifecycle.py (yes) | — | — | 5 monitor / 1 page | — | monitor_or_display_only, outcome_without_research |
| support_volatility_intelligence.json | support_volatility_intelligence.py (yes) | scripts/options_opportunity_context.py:21 | scripts/support_volatility_outcome_memory.py:15 | 3 monitor / 1 page | options_opportunity_context.py | — |
| support_volatility_outcome_memory.json | support_volatility_outcome_memory.py (yes) | — | — | 1 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| system_status.json | system_status_center.py (yes) | scripts/server_action_engine.py:19 | — | 8 monitor / 2 page | server_action_engine.py | — |
| trend_pulse_backtest.json | backtest_trend_pulse.py (yes) | — | — | 2 monitor / 0 page | — | monitor_or_display_only, outcome_without_research |
| v615_program_status.json | research_program_status.py (yes) | — | — | 0 monitor / 1 page | — | monitor_or_display_only |
| walk_forward_replay.json | walk_forward_replay.py (yes) | — | scripts/challenger_experiment_runner.py:23<br>scripts/controlled_learning_policy.py:20<br>scripts/forward_learning_feedback.py:21 | 2 monitor / 1 page | autonomous_research_planner.py | — |
| weekly_research_report.json | weekly_research_report.py (yes) | — | — | 0 monitor / 0 page | — | no_consumer |
