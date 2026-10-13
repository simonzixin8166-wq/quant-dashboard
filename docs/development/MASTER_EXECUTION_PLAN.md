# MyAlpha View — Master Execution Plan

Source of truth: `docs/development/master_plan.json` (this file is rendered by `scripts/master_plan.py render`). Last updated 2026-10-13T06:20Z. Issue: https://github.com/simonzixin8166-wq/quant-dashboard/issues/133. Charter: CLAUDE.md (owner-confirmed 2026-10-11).

Status counts: Done 19 · In progress 10 · Waiting 7 · Not started 4

Stages per task: instruction_published → claude_acked → code_merged → schedule_verified → oos_validated (oos_validated is never claimed while Learning is UNPROVEN).

## Working method

Unified ledger → continuous development by dependency → batch acceptance → update remaining tasks → next batch. Every new owner instruction is added here first (mapped to tasks, superseded items marked), never silently dropped.

## Guardrails

- Zero new paid APIs / data / services without prior owner approval; public-repo GitHub Actions minutes only
- No automatic orders, broker order APIs, or changes to production thresholds, the owner's allocation, gold/DCA rules or private positions
- Private accounts and positions never published; no long-term storage of third-party full text; respect access restrictions (robots) and copyright
- Append-only evidence; never rewrite git history or delete historical evidence
- Genuine Forward (fo-1.0), promoted forward and Auto Research Shadow are three separate tracks, never summed
- Author self-reported trades are never 'verified'
- Engineering QA PASS != Learning PASS; Learning stays UNPROVEN / FINAL=NO until matured out-of-sample evidence
- This ledger is maintained by hand from real PRs and runs; its counts are not learning metrics

## Execution capability (truthful limits)

- **hourly_watcher**: cloud scheduled task trig_01P3Sk5tEfTuAQWAdFysJKcV (minute 44 every hour): acts only when a new owner instruction on #133 is not yet referenced by a Claude comment
- **one_shot**: cloud scheduled task trig_01QwLXu1zXvSHWyZn8Y1Est2 at 2026-10-13T01:30Z: P0 day-1 report, then Batch B continuously
- **limits**: no permanent unattended coding beyond these triggers; chat uploads are readable only by the session that received them

## Owner instructions

| comment | summary | status |
|---|---|---|
| [6107376896](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6107376896) | Long-term charter M1–M4 | active |
| [6109291884](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6109291884) | Daily autonomous research (server, no Claude, no paid API) | active |
| [6109444028](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6109444028) | P0: auto research job, SEC facts, weekly report | active |
| [6109652253](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6109652253) | P0: SEC fix → real schedule → cross-day revisit | active |
| [6109685556](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6109685556) | Priority supplement: health gate, divergence, D/E/F | partly superseded by 6117163110 |
| [6109957428](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6109957428) | Delayed background dev: CDN, homepage row, SEC merge, learning audit | done |
| [6116685851](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6116685851) | Proceed: P0 verification, P1-A SEC, P1-B audit, P1-C small fixes | active |
| [6116717888](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6116717888) | Full-module collaboration audit | active |
| [6116804482](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6116804482) | Continue autonomously; self-reporting | active |
| [6116972263](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6116972263) | Experience feedback loop B1–B4 | active |
| [6117163110](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6117163110) | Unified daily plan; P0-A contamination block | active |
| [6117308392](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6117308392) | Cadence: continuous batches, one report per batch | active |
| [6117622847](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6117622847) | STOOQ 19-symbol pack import + daily maintenance | active |
| [6117657723](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6117657723) | Decouple research/data-collection universe from display watchlist; free OHLCV for all | active |
| [6117671408](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6117671408) | Create and maintain this Master Execution Plan | active |
| [6137485275](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6137485275) | P0 emergency: Daily stuck, restore 2026-10-12 + QA; pause Batch B until stable | active |
| [6137639898](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6137639898) | P1 research (after P0): BrightLine 8524 + CPI/FOMC/election/refunding windows, Shadow thesis | active |
| [6138128707](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6138128707) | P2 compliance: shared footer, sources & copyright / risk / correction pages, per-item provenance | active (waiting for production stability) |
| [6138710630](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6138710630) | R-01/R-02 full-text analysis + event windows; OPT-01 options Shadow in parallel | active |
| [6138763764](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6138763764) | BrightLine 8524 seven-section outline; three-tranche Shadow rules; R-A/R-B/R-C | active |
| [6138793593](https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6138793593) | Homepage-visible macro event reminder (H-01..H-03) as R-02 acceptance | active |

## P0 site reliability

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-01 | CDN pinning + SRI + safe fallback | **Done** | published, acked, merged | — | #198 971aabb; Autonomous QA 38151773984 workflow_dispatch overall=PASS vendor_libs=desktop:ok/mobile:ok | real libraries load at 1440/390 under SRI; stubs only on outage | keep vendor_libs in every QA | 2026-10-11T16:20Z |
| P0-02 | Homepage row 「MyAlpha 今日研究」 + QA check + 404 fix | **Done** | published, acked, merged | P0-01 | #199 063b521; #201 419bb0f; #202 e49e655; Autonomous QA 38153142070 overall=PASS research_row=desktop:ok(21)/mobile:ok(21) http_errors=0 | row renders from digest at both widths, 0 HTTP/console errors | verify digest moves to 2026-10-12 after the first schedule | 2026-10-11T16:45Z |
| P0-03 | module_failures false 'missing' incident | **Done** | published, acked, merged, schedule✓ | — | #200 05629ef; operational_incidents.jsonl resolved ded111b9461b00ae4fbc at 2026-10-11T15:44:46Z; open incidents 0 | incident closed via append-only resolved event | — | 2026-10-12T04:25Z |
| P0-INC-1013 | P0 incident 2026-10-13: Daily blocked by contract checks after SPY/10-12 data; site stuck at 2026-10-09 | **Done** | published, acked, merged | — | #217 52c968a market funnel: one maturity floor (benchmark_evaluated(3) > independently_matured(0)); #218 27b64a9 event/options funnel units (independently_matured(4) > effective_forward_eligible(0)); #220 7e7bd24 test_daily_research_job hermetic as-of (KeyError 'AVGO' once archive had 10-12); #219 d903a41 forward intake: live rule pending until its baseline session is validated (live_rule_missing_eventscore_event); #221 e842334 system status counts labeled recovery runs (system_status_untrusted); failed: Daily 38286775573 sched, 38313360410 dispatch, 38337973679 sched, 38340669182 dispatch, 38342134443 dispatch; REU 38339531830 sched; QA 38313545826 sched, 38338960799, 38344041138, 38344082295, 38345028628; recovered: Daily 38343250454 workflow_dispatch success → e17de42 updated=2026-10-13 spy_date=2026-10-12, 26/26 stocks bars 2026-10-12 with real OHLC; REU 38344089920 push success; Watchdog 38344299253 dispatch success; SIV 38344773276 dispatch → system_status overall=ok; Server Action Watch 38345184911 dispatch → judgment_basis=evaluated; QA 38345224979 workflow_run overall=PASS (business_data, server_action, investment_data_qa, decision_readiness PASS; fatal_console_errors=0, http_errors=0, deploy_matches_head=true) | Daily commits the latest completed session; QA overall=PASS; no test skipped or removed; recovery dispatch never reported as a schedule | watch the next event=schedule Daily (2026-10-13 session) | 2026-10-13T04:20Z |

## P0 data contamination

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-04 | Unverified author self-reported trades gated out of learning inputs | **Done** | published, acked, merged | — | #205 1ee856d; #206 29913fb; Source Intelligence Validation 38200101473 push: V6 brief counter-evidence citations 2→0; 38201367795 push: event-window rows labelled unverified | all 7 paths gated (author_claim_contamination.json all_gated=true); contract test fails CI on a new ungated consumer | keep test_author_claim_contract green; gate legacy extraction at source (W-02) | 2026-10-12T03:55Z |

## P0 unattended verification

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-05 | First real scheduled Auto Research run + cross-day revisit | **In progress** | published, acked, merged | — | #194; #195 31db0b9; #196 3fe9254; #217 52c968a; #218 27b64a9; #220 7e7bd24; #221 e842334; day 1 (session 2026-10-12) = FAIL/DEGRADED: Daily 21:30Z cron never fired (GAP); schedule 38286775573 (17:49Z, delayed 08:15 slot) and 38337973679 (02:40Z) failed at the verify contract; MyAlpha Auto Research 00:35Z fallback cron never fired (GAP); guardian dispatches 38313360410, 38340669182 failed (same contract); published by RECOVERY workflow_dispatch 38343250454 (not a schedule): market_as_of 2026-10-12, 8 new hypotheses, 2 abstentions (DRAM, SPCX), 21 cross-day revisits of 2026-10-09 hypotheses (14 still_valid / 5 superseded / 2 invalidated), SPY first hypothesis (not a revisit), 5 sec_correction annotations, digest latest_session 2026-10-12, weekly gaps 0; QA 38345224979 workflow_run overall=PASS research_row ok(22) vendor_libs ok | five consecutive sessions published by event=schedule runs (recovery dispatches never count), cross-day revisits, digest ok, QA PASS, GAPs recorded | day 2: session 2026-10-13 must be published by an event=schedule run; P0 incident fixes in place (waiting: 2026-10-13 NYSE close → Daily 21:30Z / guardian / Auto Research fallback) | 2026-10-13T04:20Z |
| P0-06 | Five consecutive trading days of unattended reliability | **Waiting** | published, acked | P0-05 | — | 5 sessions with schedule runs or recorded GAP + recovery | daily check (waiting: sessions 2026-10-12..10-16) | 2026-10-12T04:25Z |

## P0 data quality

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-07 | SEC fundamentals quality gate (period, freshness, anomaly_review) | **Done** | published, acked, merged | — | #195 31db0b9; #196 3fe9254; MyAlpha Auto Research 38144873589 / 38145180529 workflow_dispatch sec_only | AVGO/NVDA/GOOG/IREN/TSM fixed or unavailable; anomalies held for review | pre-gate SEC evidence labelled until superseded (P0-05 run appends sec_correction) | 2026-10-11T14:00Z |

## B1 experience

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B1-02 | precedents / error_attribution / experience_input_status in daily_research_job (used_in_decision=false) | **In progress** | published, acked, merged | P0-05, B1-01 | #213 201d2a3 (B1-02, auto-research-5); #223 4fe2940 (weekly report no longer counts same-session generator re-runs); MyAlpha Auto Research 38345865213 workflow_dispatch 'post-P0 B1 activation' (not a schedule): 8 server-written hypotheses for 2026-10-12 carry precedents/error_attribution/experience_input_status, used_in_decision=false; distinct symbol-sessions with experience = 8; MSFT 10 precedents (status used); GOOG 5; SPY 4; TSM 8; NBIS/NVDA/QQQ/QQQM 0 (status none); ORCL / VGT / AMD: no server record yet — their 2026-10-09 hypotheses were revisited still_valid, so no new hypothesis was generated; they get experience on their next new hypothesis; module_manifest experience_citation: not yet wired → wired (8 records) | server-generated records with precedents/error_attribution for real symbols; ORCL/VGT/AMD verified when they next form a hypothesis | verify ORCL/VGT/AMD server records when they next form a hypothesis (AMD expected 0 precedents) | 2026-10-13T04:45Z |
| B1-01 | Precedent data quality and timing audit | **Done** | published, acked, merged | — | #206 29913fb; research/audit/p1_readiness.json: 84 usable of 160, look-ahead 0 | usable precedents counted with no look-ahead; spec written | B1-02 | 2026-10-12T03:50Z |

## Data universe

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| D-05 | Free daily OHLCV collection for the data_collection_universe incl. the 19 STOOQ symbols (not tied to the display list) | **In progress** | published, acked, merged | D-04, D-06, P0-05 | #225 1eb2215; dry run on real state: 26 symbols from docs/data.json; 14 not on the site (AAOI AAPL CRWV DIA GLD HYG IWM META MU NOW TLT XLE XLF XLK) request the free Yahoo fallback (basis-checked); not verifiable in the sandbox (no egress) | after a real schedule Daily a non-displayed symbol (e.g. AAPL) shows a 2026-10-13+ bar from the fallback, or is recorded missing/stale with the reason | check the next event=schedule Daily (session 2026-10-13) (waiting: Daily schedule 2026-10-13 21:30Z) | 2026-10-13T04:45Z |
| D-01 | SPY daily history in the canonical archive | **Done** | published, acked, merged | — | #207 cadfbc1; local dry run: macro_outcome_memory → waiting_for_mature_outcomes; market_state_outcome_scorecards matured 4 outcomes | validated, provenance recorded (data/history/spy_provenance.json), other members byte-identical | D-02 — *disclosure:* merged 2026-10-12T04:07Z, before 6117622847 (04:13Z) asked to keep the base archive unchanged until after the first schedule; SPY is a new research symbol on 2026-10-12 and its first hypothesis is not a cross-day revisit | 2026-10-12T04:10Z |
| D-02 | SPY / TQQQ daily increments with real OHLC | **Done** | published, acked, merged, schedule✓ | D-01 | Daily 38343250454 workflow_dispatch (recovery): archive SPY 2026-10-12 O778.78 H779.40 L777.05 C778.10 V18.6M and TQQQ O80.78 H80.81 L79.22 C79.61 V31.3M = docs/data.json stocks.*; macro_outcome_memory waiting_for_mature_outcomes (obs 5, matured 0); market_state_outcome_scorecards learning_active (7 outcomes, 3 scorecards, all 5-session = early reads) | 2026-10-12 bars appended from docs/data.json stocks.SPY / stocks.TQQQ (owner added both to the watchlist) with open/high/low not all equal to close | append written by a recovery dispatch, not a schedule; re-check on the next schedule | 2026-10-13T04:20Z |
| D-03 | STOOQ 19-symbol pack import (MyAlpha_STOOQ_19symbols_20261009.zip) | **Done** | published, acked, merged | P0-05 | #212 a201413 (script); #224 c960494 (import); pack sha256 ead9bb5f… verified from data-handoff/stooq-20261009 (branch not merged); dry run → --apply → re-run 0 changes; 16 appended (AAOI AAPL AMZN CRWV DIA GLD HYG INTC IWM META MU NOW TLT XLE XLF XLK); SPY skipped identical; 8 corrections (TQQQ 5 flat bars → real OHLCV, LITE 09-29/30 + 10-01) in data/history/corrections.jsonl; symbol_registry missing securities 16 → 0; event rows without history 222 → 0 | manifest SHA-256 re-verified; per-symbol checks; overlap vs existing archive; conflicts quarantined; append-only; provenance per file | none (new symbols' first hypotheses are not revisits; nothing backfilled as Genuine Forward) | 2026-10-13T04:45Z |
| D-04 | Symbol registry generator: research_universe / data_collection_universe / display_watchlist (read-only) | **Done** | published, acked, merged | — | this PR (D-04/D-07/D-06 prep); research/audit/symbol_registry.json: display 28, research 30, collection 40, in archive 24 (fresh), missing 16 securities (all covered by the staged owner pack); 222 event rows without history reported separately; AAPL collected though not displayed; DRAM identity unverified; SPCX = SEC "SPACE EXPLORATION TECHNOLOGIES CORP." | three universes separated; hidden securities stay in the collection universe; identity never guessed; test_symbol_registry | wiring into the daily collector is D-05 | 2026-10-12T05:00Z |
| D-06 | Stop synthetic flat bars from close-only rows (TQQQ 5 of last 30) | **Done** | published, acked, merged | P0-05 | #211 e34ad9c (module); #225 1eb2215 (wired); dashboard_bar no longer back-fills close into O/H/L; close-only → close_only, never written; conflicts quarantined; legacy test assertion replaced | close-only rows never written as full bars; existing H=L=C bars compared with source (real flat days possible) and corrected only via logged replacement | watch the next schedule report for close_only / quarantined entries | 2026-10-13T04:45Z |
| D-07 | Import validator + Missing Historical Symbols manifest (distinct securities; AAPL, AMZN, AAOI, INTC, MU, META, NOW, CRWV; identity checks for DRAM/SPCX) | **Done** | published, acked, merged | — | #209 de2460f; this PR; missing_historical_symbols in symbol_registry.json: 16 distinct securities (MU, INTC, AMZN, META, NOW, CRWV, AAOI, AAPL + 8 benchmark ETFs); all in the validated owner pack | distinct securities with use_case, source, priority, identity; event rows reported separately | re-run after D-03 import (expected missing → 0) | 2026-10-12T05:00Z |

## B2 outcomes

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B2-02 | Wire the clean fundamentals-outcome subset as historical reliability context | **In progress** | published, acked, merged | B1-02 | #226 59cbe07 (auto-research-6); #228 369f7b7 (provenance → manifest sees the consumer); clean subset recount: 223/220 matured 20/60 (100/97 with revenue YoY); 370/772 observations excluded (RUB, YTD); today every symbol is descriptive_pooled_only (e.g. MSFT n=16, pooled n=73, positive rate 0.60 @20); market-state scorecards not wired (5-session only, n<30); other memories disconnected with reasons | only USD quarter/annual observations; n shown; others disconnected with reason | verify server-written auto-research-6 records carry historical_reliability after the next schedule (waiting: Daily schedule 2026-10-13) | 2026-10-13T04:45Z |
| B2-03 | Macro / market-state / event / options / support outcomes reach maturity | **Waiting** | published, acked | D-01 | — | matured counts from real future sessions only; n ≥ 30 before research use | re-run p1_readiness weekly (waiting: event 5d from 2026-10-13, options 5d from 2026-10-14, macro/support 20d from 2026-11-04) | 2026-10-12T04:25Z |
| B2-01 | Six outcome memories quality / maturity audit | **Done** | published, acked, merged | — | #206 29913fb; #207 cadfbc1; p1_readiness.json: fundamentals clean subset 189/186; event/options/support pending; macro/market_state pending after SPY | verdict per memory with reason | B2-02 | 2026-10-12T04:10Z |

## B4 SEC

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B4-02 | Unified SEC fetcher + append-only fundamentals_v2 + shadow old-schema file (dual run) | **In progress** | published, acked, merged | P0-05, B4-01 | #227 3aa76fd; Daily step 'SEC unified fact fetcher v2 (Shadow) + daily reconciliation' (non-blocking); no consumer migrated; SEC not reachable from the sandbox | all candidate concepts, USD only, period_kind, filed, accn, quality_flags; union universe; old files untouched | verify the first real v2 Shadow run (research/archive/fundamentals_v2, shadow_v2_vs_new) after the next Daily (waiting: Daily schedule 2026-10-13) | 2026-10-13T04:45Z |
| B4-03 | One real trading day comparison, then compatible consumer migration | **Not started** | published | B4-02 | — | unexplained differences 0; old observations get quality flags only | after B4-02 runs one session | 2026-10-12T04:25Z |
| B4-01 | SEC dual-source read-only reconciliation | **Done** | published, acked, merged | — | #203 4b523ce; sec_fact_reconciliation.json: overlap 7, agreement 2/7 | every difference classified | B4-02 | 2026-10-12T02:40Z |

## B3 collaboration

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B3-01 | Shared evidence contract between V6 planner/executor and Auto Research (ledgers stay separate) | **Not started** | published, acked | B1-02, B4-02 | — | both streams cite the same evidence ids; V6 views enter Shadow only when locked and versioned | after B1/B4 | 2026-10-12T04:25Z |

## Modules

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| M-02 | Repair the 21 learning/outcome artifacts with no research consumer (value first) | **In progress** | published, acked | B1-02, B2-02 | #226; #228; module_manifest: reaching research 13 → 14; outcome_without_research 21 → 20 (15 excluding 5 frozen stages); experience_citation wired | count falls with real consumers; ineffective modules frozen not forced | re-run manifest after each batch | 2026-10-13T04:45Z |
| M-04 | Weekly manifest / learning-chain trend report | **Not started** | published | M-01 | — | weekly scheduled run writes broken-link counts and changes | wire module_manifest_audit into an existing weekly workflow | 2026-10-12T04:25Z |
| M-01 | Module manifest + 15-module matrix | **Done** | published, acked, merged | — | #204 0b52fc6; module_manifest.json: 34 learning/outcome, 13 reach research, experience citation not yet wired | roles reviewed per reader; CI fails on an unclassified reader | M-02 | 2026-10-12T03:00Z |
| M-03 | Freeze 5 downstream candidate stages (no deletion) | **Done** | published, acked, merged | P0-05 | #228 369f7b7; 5 stages frozen in research/registry/frozen_modules.json; flagged in module_manifest; unfreeze_due=false | flagged and skipped in weekly review; evidence kept | unfreeze when candidate_forward_status eligible_candidates > 0 | 2026-10-13T04:45Z |

## WXC collection

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| W-01 | wxc-bot research-close daily + 13:10 UTC catch-up cron | **In progress** | published, acked, merged | — | wxc-bot #54 1341835; research-close 38312386852 schedule success (created 21:43Z, most likely the 13:10Z slot delayed ~8.5h) → commit d881f15; 22:30Z slot: run created 03:07Z 2026-10-13 schedule success (delayed ~4.5h) | event=schedule runs at 13:10 and 22:30 UTC | both slots ran but both heavily delayed by GitHub; keep watching | 2026-10-13T04:20Z |
| W-02 | Gate legacy author-operation extraction at source (ce-5 or review before evidence) | **Not started** | published, acked | P0-04 | — | legacy operations reach evidence only after ce-5 or review | wxc-bot PR | 2026-10-12T04:25Z |

## WXC understanding

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| W-03 | M1 understanding: blind labels test v2 (41) / v3 (28) → κ; long-article frozen test | **Waiting** | published, acked | — | — | κ computed on independent labels; rules changed only on dev | needs independent labels (waiting: GPT/owner blind labels) | 2026-10-12T04:25Z |

## Operations

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| OPS-01 | Cloud instruction watcher + one-shot P0/Batch B task | **Done** | published, acked, merged | — | trig_01P3Sk5tEfTuAQWAdFysJKcV hourly; trig_01QwLXu1zXvSHWyZn8Y1Est2 2026-10-13T01:30Z (cloud, not device-bound) | watcher acts only on unreferenced owner instructions; ledger baseline on #133 6116834357 | check watcher run history | 2026-10-12T04:25Z |

## Owner decisions

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| OWN-01 | Owner: confirm GEMINI_API_KEY billing (two manual Gemini workflows) | **Waiting** | acked | — | — | owner answer | — (waiting: owner) | 2026-10-12T04:25Z |
| OWN-02 | Owner: delete leftover branch tmp/vendor-probe | **Waiting** | acked | — | — | branch gone | — (waiting: owner (branch deletion not permitted from this environment)) | 2026-10-12T04:25Z |
| OWN-03 | Owner: logged-in check of options assignment-preference cards and private stock ledger save | **Waiting** | acked | — | — | owner confirms | — (waiting: owner login) | 2026-10-12T04:25Z |
| OWN-04 | Owner: authorize publishing the 19-symbol pack in the public repo (file already received in this chat) | **Done** | acked, merged | — | owner authorization in the Claude chat 2026-10-12 12:33 (UTC+8); recorded on #133; pack staged on branch data-handoff/stooq-20261009 @ fe2af73 (sha256 ead9bb5f…) | file received + explicit authorization | — (waiting: owner) | 2026-10-12T04:40Z |

## Research tasks

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| OPT-01 | Options blogger Sell Put / Covered Call management — Shadow research and decision comparison (no orders) | **In progress** | published, acked | — | — | author strategy marked source_pending unless the original material is accessible; MyAlpha independent framework (Delta/DTE/IV/earnings/ex-div/assignment, close-early/hold/roll/assigned paths) with stress scenarios; per-account analysis kept private; no claim of verified win rates; no orders, no threshold changes | report on #133 today (aggregate only); per-position details in the private ledger repo | 2026-10-13T06:20Z |
| R-01 | BrightLine 8524 provenance check + pre-registered falsifiable 'bottom within ~3 weeks' Shadow thesis + official event windows | **In progress** | published, acked | P0-INC-1013 | #230 3deebc5 (v0.1); this PR: v0.2 fact matrix + Chinese report + tranche state machine (R-A/R-B); wxc-bot feed record 56cd7e041adfe7bc43dc captured 2026-10-13T03:10:58Z (scheduled_blog_scan_complete, 3315 chars seen, 360-char excerpt persisted); source_store admission_class=genuine_forward; official checks 2026-10-13: Fed 09-16 statement (3¾–4%, 12–0), BLS jobs 10-02 (+29k, 4.2%), CPI Aug (3.4%/2.4%), Treasury sb0607 buybacks; 10Y FRED 10-08 5.22%; MyAlpha breadth b200 51.9% (10-12) | R-A Chinese section-by-section fact/opinion/counter-evidence matrix with official sources and as_of; full text status honest (partial unless read at runtime); v0.1 definitions only revised by version; R-B rules locked with tests (fail-closed, AND/OR fidelity, no allocation inference) | R-C daily observation after real sessions; record official outcomes in research/macro_events/event_facts_2026q4.json after each event | 2026-10-13T06:20Z |
| R-02 | Event-offset monitor (T-1..T+10) for CPI / FOMC / refunding / election with stale-aware confirm/conflict/pending output | **In progress** | published, acked | R-01 | — | homepage-visible compact reminder (H-01 fixtures → H-02 real artifact before CPI 10-14 08:30 ET → H-03 real T..T+10 checkpoints with Actions run IDs); ET (DST-aware) + Beijing times; stale/failed shown, never an optimistic carry-over; desktop + 390px QA; no BUY/SELL; gold/DCA layout untouched | H-01 now (isolated read-only PR); H-02 wiring after tonight's schedule acceptance | 2026-10-13T06:20Z |

## Compliance & UX

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| C-01 | Shared footer (sources/copyright, risk disclaimer, correction & contact) + full Chinese policy page + per-item provenance labels | **Waiting** | published, acked | P0-INC-1013 | — | PR/CI/Pages/QA PASS; desktop + 390px; three links clickable, no 404; homepage gold/DCA layout, feedback email, APP_VERSION 6.9.0 unchanged; no claim of authorization; any non-compliant full-text cache raised separately | implement once the scheduled Daily is green (waiting: production stability: first successful event=schedule Daily after the P0 (2026-10-13 session) + QA PASS) | 2026-10-13T05:00Z |

Engineering QA PASS ≠ Learning PASS. **Learning UNPROVEN / FINAL=NO.**
