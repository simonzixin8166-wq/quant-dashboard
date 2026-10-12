# MyAlpha View — Master Execution Plan

Source of truth: `docs/development/master_plan.json` (this file is rendered by `scripts/master_plan.py render`). Last updated 2026-10-12T05:40:00Z. Issue: https://github.com/simonzixin8166-wq/quant-dashboard/issues/133. Charter: CLAUDE.md (owner-confirmed 2026-10-11).

Status counts: Done 14 · In progress 4 · Waiting 13 · Not started 4

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

## P0 site reliability

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-01 | CDN pinning + SRI + safe fallback | **Done** | published, acked, merged | — | #198 971aabb; Autonomous QA 38151773984 workflow_dispatch overall=PASS vendor_libs=desktop:ok/mobile:ok | real libraries load at 1440/390 under SRI; stubs only on outage | keep vendor_libs in every QA | 2026-10-11T16:20Z |
| P0-02 | Homepage row 「MyAlpha 今日研究」 + QA check + 404 fix | **Done** | published, acked, merged | P0-01 | #199 063b521; #201 419bb0f; #202 e49e655; Autonomous QA 38153142070 overall=PASS research_row=desktop:ok(21)/mobile:ok(21) http_errors=0 | row renders from digest at both widths, 0 HTTP/console errors | verify digest moves to 2026-10-12 after the first schedule | 2026-10-11T16:45Z |
| P0-03 | module_failures false 'missing' incident | **Done** | published, acked, merged, schedule✓ | — | #200 05629ef; operational_incidents.jsonl resolved ded111b9461b00ae4fbc at 2026-10-11T15:44:46Z; open incidents 0 | incident closed via append-only resolved event | — | 2026-10-12T04:25Z |

## P0 data contamination

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-04 | Unverified author self-reported trades gated out of learning inputs | **Done** | published, acked, merged | — | #205 1ee856d; #206 29913fb; Source Intelligence Validation 38200101473 push: V6 brief counter-evidence citations 2→0; 38201367795 push: event-window rows labelled unverified | all 7 paths gated (author_claim_contamination.json all_gated=true); contract test fails CI on a new ungated consumer | keep test_author_claim_contract green; gate legacy extraction at source (W-02) | 2026-10-12T03:55Z |

## P0 unattended verification

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-05 | First real scheduled Auto Research run + cross-day revisit | **Waiting** | published, acked, merged | — | #194; #195 31db0b9; #196 3fe9254; no event=schedule research run yet (weekend) | event=schedule Daily/Auto Research run IDs, market_as_of 2026-10-12, real cross-day revisits (same-day supersedes excluded), digest ok, QA PASS, GAP recorded | cloud task 2026-10-13T01:30Z reports day 1 (waiting: 2026-10-12 NYSE close → Daily 21:30Z / fallback 00:35Z) | 2026-10-12T04:25Z |
| P0-06 | Five consecutive trading days of unattended reliability | **Waiting** | published, acked | P0-05 | — | 5 sessions with schedule runs or recorded GAP + recovery | daily check (waiting: sessions 2026-10-12..10-16) | 2026-10-12T04:25Z |

## P0 data quality

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| P0-07 | SEC fundamentals quality gate (period, freshness, anomaly_review) | **Done** | published, acked, merged | — | #195 31db0b9; #196 3fe9254; MyAlpha Auto Research 38144873589 / 38145180529 workflow_dispatch sec_only | AVGO/NVDA/GOOG/IREN/TSM fixed or unavailable; anomalies held for review | pre-gate SEC evidence labelled until superseded (P0-05 run appends sec_correction) | 2026-10-11T14:00Z |

## B1 experience

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B1-02 | precedents / error_attribution / experience_input_status in daily_research_job (used_in_decision=false) | **In progress** | published, acked | P0-05, B1-01 | #213 (DRAFT, not merged); research/audit/b1_replay_preview.json (local preview, not journal records): MSFT 10 precedents; ORCL 5, all conflicting with its bearish view; VGT 5; AMD 0 precedents + 2 market error cases | server-generated replayable records for MSFT, ORCL, VGT (AMD = none); counts by distinct symbol-session; experience_citation flips to wired in module_manifest | after P0-05: mark #213 ready, merge, let the server generate auto-research-5 records; verify module_manifest experience_citation flips to wired with server records (waiting: P0-05 (generator must not change before the first schedule)) | 2026-10-12T05:40Z |
| B1-01 | Precedent data quality and timing audit | **Done** | published, acked, merged | — | #206 29913fb; research/audit/p1_readiness.json: 84 usable of 160, look-ahead 0 | usable precedents counted with no look-ahead; spec written | B1-02 | 2026-10-12T03:50Z |

## Data universe

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| D-03 | STOOQ 19-symbol pack import (MyAlpha_STOOQ_19symbols_20261009.zip) | **In progress** | published, acked | P0-05 | this PR: scripts/stooq_pack_import.py (dry-run default, --apply) + tests/test_stooq_pack_import.py; pack received in this Claude chat 2026-10-12T04:24Z, sha256 ead9bb5f…; manifest sha256 19/19 match; research/audit/stooq_pack_validation.json: new clean 11 (AMZN, META, NOW, DIA, GLD, HYG, IWM, TLT, XLE, XLF, XLK); SPY identical to #207; review 7; dry run on a copy of the real archive: 25→41 members, only TQQQ/LITE changed, 8 corrections (TQQQ 5 flat bars, LITE 09-29/30 + 10-01 inserted), re-run 0 changes; real archive untouched | manifest SHA-256 re-verified; per-symbol checks; overlap vs existing archive; conflicts quarantined; append-only; provenance per file | after P0-05: git fetch data-handoff/stooq-20261009 → python -I scripts/stooq_pack_import.py <zip> --apply → python scripts/local_history_agent.py → symbol_registry.py (missing → 0) → PR (waiting: P0-05 only (owner authorized publishing; pack staged on branch data-handoff/stooq-20261009)) | 2026-10-12T05:15Z |
| D-06 | Stop synthetic flat bars from close-only rows (TQQQ 5 of last 30) | **In progress** | published, acked | P0-05 | this PR: scripts/ohlcv_merge.py + tests/test_ohlcv_merge.py (not wired); legacy dashboard_bar close-only back-fill pinned by test as the defect to remove | close-only rows never written as full bars; existing H=L=C bars compared with source (real flat days possible) and corrected only via logged replacement | after P0-05: local_history_agent.append_latest uses ohlcv_merge for the data_collection_universe; flat bars fixed only via corrections.jsonl (TQQQ from owner pack) (waiting: P0-05 (production pipeline change)) | 2026-10-12T05:00Z |
| D-02 | SPY / TQQQ daily increments with real OHLC | **Waiting** | published, acked | D-01 | — | 2026-10-12 bars appended from docs/data.json stocks.SPY / stocks.TQQQ (owner added both to the watchlist) with open/high/low not all equal to close | verify in the P0-05 report (waiting: Daily schedule 2026-10-12) | 2026-10-12T04:25Z |
| D-05 | Free daily OHLCV collection for the data_collection_universe incl. the 19 STOOQ symbols (not tied to the display list) | **Waiting** | published, acked | D-04, D-06, P0-05 | — | a symbol not shown on the site (e.g. AAPL) still updates after a real schedule; missing source → missing/stale, never synthesized; idempotent | after P0-05: collector iterates symbol_registry data_collection_universe; full-OHLC sources only; missing/stale recorded; verify AAPL/AMZN update after a real schedule (waiting: P0-05 (no canonical-archive pipeline change before the first schedule)) | 2026-10-12T04:25Z |
| D-01 | SPY daily history in the canonical archive | **Done** | published, acked, merged | — | #207 cadfbc1; local dry run: macro_outcome_memory → waiting_for_mature_outcomes; market_state_outcome_scorecards matured 4 outcomes | validated, provenance recorded (data/history/spy_provenance.json), other members byte-identical | D-02 — *disclosure:* merged 2026-10-12T04:07Z, before 6117622847 (04:13Z) asked to keep the base archive unchanged until after the first schedule; SPY is a new research symbol on 2026-10-12 and its first hypothesis is not a cross-day revisit | 2026-10-12T04:10Z |
| D-04 | Symbol registry generator: research_universe / data_collection_universe / display_watchlist (read-only) | **Done** | published, acked, merged | — | this PR (D-04/D-07/D-06 prep); research/audit/symbol_registry.json: display 28, research 30, collection 40, in archive 24 (fresh), missing 16 securities (all covered by the staged owner pack); 222 event rows without history reported separately; AAPL collected though not displayed; DRAM identity unverified; SPCX = SEC "SPACE EXPLORATION TECHNOLOGIES CORP." | three universes separated; hidden securities stay in the collection universe; identity never guessed; test_symbol_registry | wiring into the daily collector is D-05 | 2026-10-12T05:00Z |
| D-07 | Import validator + Missing Historical Symbols manifest (distinct securities; AAPL, AMZN, AAOI, INTC, MU, META, NOW, CRWV; identity checks for DRAM/SPCX) | **Done** | published, acked, merged | — | #209 de2460f; this PR; missing_historical_symbols in symbol_registry.json: 16 distinct securities (MU, INTC, AMZN, META, NOW, CRWV, AAOI, AAPL + 8 benchmark ETFs); all in the validated owner pack | distinct securities with use_case, source, priority, identity; event rows reported separately | re-run after D-03 import (expected missing → 0) | 2026-10-12T05:00Z |

## B2 outcomes

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B2-02 | Wire the clean fundamentals-outcome subset as historical reliability context | **Waiting** | published, acked | B1-02 | — | only USD quarter/annual observations; n shown; others disconnected with reason | Batch B (waiting: B1-02) | 2026-10-12T04:25Z |
| B2-03 | Macro / market-state / event / options / support outcomes reach maturity | **Waiting** | published, acked | D-01 | — | matured counts from real future sessions only; n ≥ 30 before research use | re-run p1_readiness weekly (waiting: event 5d from 2026-10-13, options 5d from 2026-10-14, macro/support 20d from 2026-11-04) | 2026-10-12T04:25Z |
| B2-01 | Six outcome memories quality / maturity audit | **Done** | published, acked, merged | — | #206 29913fb; #207 cadfbc1; p1_readiness.json: fundamentals clean subset 189/186; event/options/support pending; macro/market_state pending after SPY | verdict per memory with reason | B2-02 | 2026-10-12T04:10Z |

## B4 SEC

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B4-02 | Unified SEC fetcher + append-only fundamentals_v2 + shadow old-schema file (dual run) | **Waiting** | published, acked | P0-05, B4-01 | — | all candidate concepts, USD only, period_kind, filed, accn, quality_flags; union universe; old files untouched | Batch B (waiting: P0-05) | 2026-10-12T04:25Z |
| B4-03 | One real trading day comparison, then compatible consumer migration | **Not started** | published | B4-02 | — | unexplained differences 0; old observations get quality flags only | after B4-02 runs one session | 2026-10-12T04:25Z |
| B4-01 | SEC dual-source read-only reconciliation | **Done** | published, acked, merged | — | #203 4b523ce; sec_fact_reconciliation.json: overlap 7, agreement 2/7 | every difference classified | B4-02 | 2026-10-12T02:40Z |

## B3 collaboration

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| B3-01 | Shared evidence contract between V6 planner/executor and Auto Research (ledgers stay separate) | **Not started** | published, acked | B1-02, B4-02 | — | both streams cite the same evidence ids; V6 views enter Shadow only when locked and versioned | after B1/B4 | 2026-10-12T04:25Z |

## Modules

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| M-02 | Repair the 21 learning/outcome artifacts with no research consumer (value first) | **In progress** | published, acked | B1-02, B2-02 | baseline 21 (module_manifest 2026-10-12) | count falls with real consumers; ineffective modules frozen not forced | re-run manifest after each batch | 2026-10-12T04:25Z |
| M-03 | Freeze 5 downstream candidate stages (no deletion) | **Waiting** | published, acked | P0-05 | — | flagged and skipped in weekly review; evidence kept | Batch B (waiting: P0-05) | 2026-10-12T04:25Z |
| M-04 | Weekly manifest / learning-chain trend report | **Not started** | published | M-01 | — | weekly scheduled run writes broken-link counts and changes | wire module_manifest_audit into an existing weekly workflow | 2026-10-12T04:25Z |
| M-01 | Module manifest + 15-module matrix | **Done** | published, acked, merged | — | #204 0b52fc6; module_manifest.json: 34 learning/outcome, 13 reach research, experience citation not yet wired | roles reviewed per reader; CI fails on an unclassified reader | M-02 | 2026-10-12T03:00Z |

## WXC collection

| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |
|---|---|---|---|---|---|---|---|---|
| W-01 | wxc-bot research-close daily + 13:10 UTC catch-up cron | **Waiting** | published, acked, merged | — | wxc-bot #54 1341835; catch-up 38198512109 workflow_dispatch (BrightLine 7216) | event=schedule runs at 13:10 and 22:30 UTC | verify in the P0-05 report (waiting: first schedule 2026-10-12T13:10Z) | 2026-10-12T04:25Z |
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

Engineering QA PASS ≠ Learning PASS. **Learning UNPROVEN / FINAL=NO.**
