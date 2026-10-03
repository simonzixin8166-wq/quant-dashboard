# myAlphaView V5.4.0 — Learning Engine Core

## Purpose
V5.4 upgrades V5.3 historical state statistics into a reusable learning core. The system now separates:
1. point-in-time macro context;
2. current Situation snapshots;
3. historical similarity evidence;
4. Strategy Memory;
5. contradiction checks;
6. research opportunity ordering.

The engine may change research attention and warning strength. It does not place trades, size positions, or rewrite the core QQQM/VGT/QLD rules.

## New files
- `scripts/fred_client.py` — FRED/ALFRED client with real-time-period support for point-in-time replay.
- `scripts/update_fred_macro.py` — builds `docs/research/macro_context.json`.
- `scripts/learning_engine_core.py` — builds `docs/research/learning_engine.json`.
- `tests/test_v540_learning_engine_core.py` — deterministic contract tests.

## Macro layer
Initial official series:
- DFF
- DGS2 / DGS10
- T10Y2Y
- DFII10
- CPIAUCSL / CPILFESL
- PCEPI / PCEPILFE
- UNRATE / PAYEMS
- NFCI
- BAMLH0A0HYM2
- DTWEXBGS
- VIXCLS

The output converts raw observations into research regimes such as:
- rates: RISING / FALLING / STABLE
- yield curve: INVERTED / NORMALIZING / NORMAL
- inflation: HOT / STABLE / COOL
- credit: EASY / NEUTRAL / STRESSED
- financial conditions: LOOSE / NEUTRAL / TIGHT
- macro risk score: 0–100

FRED failures do not erase the last good macro evidence. Cached series are retained and explicitly marked.

## Point-in-time guardrail
Historical macro replay must request FRED/ALFRED with:
`realtime_start = realtime_end = historical date`

This prevents later revisions from leaking into an earlier Situation.

## Situation Memory
Each current Trend Pulse asset is transformed into a structured Situation containing:
- timestamp / symbol / price;
- drawdown / RSI / Trend Pulse;
- stage / weekly direction / structure / Supertrend;
- market regime;
- macro regime;
- historical stage evidence;
- similar historical situations;
- contradiction evidence;
- research priority.

## Similarity Engine V1
The first version intentionally uses transparent features:
- stage;
- Trend Pulse distance;
- weekly direction;
- zone when available.

It reports sample count, median 60-day return, 60-day positive rate, median MAE and the strongest historical matches.

This is an evidence layer, not a future-return promise.

## Strategy Memory
The mature 20/60/120-day state profiles produced by V5.3 are exposed as Strategy Memory instead of remaining only UI statistics.

## Contradiction Engine
The first rules flag conflicts such as:
- positive technical stage vs high macro risk;
- strong trend vs very high RSI;
- weak daily stage vs bullish weekly trend;
- positive stock trend vs market-breadth divergence.

## Opportunity queue
The engine produces a research-priority queue. It is deliberately named research priority rather than buy score.

The queue may incorporate:
- Trend Pulse stage;
- historical evidence adjustment;
- weekly agreement;
- macro risk;
- contradictory evidence.

It never produces account dollars, contract quantity or automatic orders.

## Daily automation
Daily Dashboard Update now:
1. builds normal market data;
2. updates STOOQ history and V5.3 historical journal;
3. updates FRED macro context using `FRED_API_KEY`;
4. builds V5.4 Learning Engine Core;
5. runs V5.3 and V5.4 tests;
6. commits generated `docs/research/` outputs with the normal daily update.

## Next expansion boundary
V5.4 Core is deliberately modular. SEC fundamental momentum, SEC company events, richer options intelligence, macro-conditioned historical replay and Error Memory can attach to the Situation schema without changing the core ETF rules.
