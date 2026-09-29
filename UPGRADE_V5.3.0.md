# myAlphaView V5.3.0 — Autonomous Learning Agent

## Purpose
V5.3 turns Decision Journal into a two-track learning system:
1. historical backfill from the user-supplied STOOQ OHLCV archive;
2. live forward journal from the actual website assistant.

The agent may learn research priority from historical outcomes, but it does not change core ETF thresholds and never places orders.

## Historical store
- `data/history/stooq_watchlist.zip`: 21 STOOQ daily OHLCV files supplied by the user.
- `scripts/local_history_agent.py`: appends only the latest already-fetched dashboard bar; it does not redownload years of data.
- `docs/research/historical_journal.json`: generated five-year state-event study used by Decision Journal and the assistant.

Historical replay is causal. Daily Trend Pulse components match the existing model; the weekly component uses the prior completed weekly bar to avoid look-ahead in historical reconstruction.

## Daily automation
`Daily Dashboard Update` now performs:
1. normal market/data build;
2. local STOOQ archive incremental append from `docs/data.json`;
3. five-year historical learning rebuild;
4. market-alert historical validation;
5. immutable build manifest;
6. tests;
7. commit of both `docs/` and the updated local history archive.

No additional historical API request is made by the local history agent.

## Decision Journal fixes
- Supabase auth waits for `window.mavSupabase` instead of failing before initialization.
- Live snapshots and candidate-row counts are separated.
- 20/60/120-day cells explicitly show `未成熟` and an approximate remaining-trading-day note.
- Historical learning is immediately visible with mature 20/60/120 samples.
- Historical state statistics include average/median return, positive-rate, MAE, MFE and average excess vs QQQ.

## Autonomous QA fixes
- Correct assistant root: `#marketOptionAlert`.
- Assistant initialization receives retries; a loaded module waiting for its first market snapshot is INFO, not FAIL.
- Private Supabase initialization receives retries.
- QA checks that the historical-learning report is deployed.

## Learning guardrails
The system may automatically:
- record;
- backfill;
- calculate outcomes;
- compare similar historical states;
- change research priority ordering;
- surface warnings and reminders.

The system may not automatically:
- change core QQQM/VGT/QLD drawdown thresholds;
- convert blogger opinions into production rules;
- infer historical option P&L from underlying returns;
- place trades or select position size for the investor.
