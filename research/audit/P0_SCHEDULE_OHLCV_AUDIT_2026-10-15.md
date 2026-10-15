# P0 audit — schedule reliability and 40-symbol OHLCV (#133 6183848571)

Evidence: `p0_schedule_ohlcv_audit_2026-10-15.json` (same folder; 80 per-symbol rows for 10-13 and 10-14).
Source: GitHub Actions REST (run_id/event/created/started/updated/head_sha/conclusion), job logs, and the git history of
`docs/research/historical_journal.json` and `data/history/stooq_watchlist.zip` on main @ 34f06af. Generated 2026-10-15 03:53Z.

## Daily (21:30Z cron) by NYSE session

| Session | Real `schedule` run | Delay | Result | Recovery (`workflow_dispatch`) | Data completeness | Verdict |
|---|---|---|---|---|---|---|
| 10-12 | 38337973679 | 5h10m | failure | guardian 38313360410 ✗, 38340669182 ✗; manual 38342134443 ✗, 38343250454 ✓ | 40/40 only at 10-13 15:54Z | **FAIL** |
| 10-13 | 38490415299 | 2h58m | success | guardian 38487322756 ✓ (first) | **26/40** after both evening runs; 40/40 at 10-14 13:51Z | **DEGRADED** |
| 10-14 | 38657460138 | 2h30m | success | guardian 38644154255 ✓ (first, 22:07Z) | 40/40 at 22:07Z | **DEGRADED** (late; recovery came first) |

P0-06 (five consecutive on-time `schedule` days): **0/5**. Recovery runs never count toward it.

The other crons were late every day too:
- Auto Research 00:35/12:35Z ran 4h41m–6h54m late. The 10-15 00:35Z run had still not fired at 03:53Z.
- The 08:15Z light Daily ran 5h24m–9h34m late. The 10-14 run executed during US hours: the guard dropped the incomplete 10-14 candle, so no intraday bar was archived.

## Root cause, ranked by evidence
1. **GitHub schedule delay (evidence).** Queue time (started − created) is 0 s for all 23 Daily/Auto Research runs since 10-11. The lateness is therefore before GitHub created the run, not a concurrency lock or a runner queue. It hit three different crons on every day. The repo is active, so the 60-day schedule auto-disable does not apply.
2. **10-12 workflow failure (evidence).** The `Verify generated dashboard contract` step failed in five runs. The earlier P0 recovery (7e7bd24) fixed it.
3. **10-13 26/40 source gap (evidence + hypothesis).**
   - Evidence: in the 00:05Z and 00:36Z runs, the yfinance batch fallback returned no 10-13 bar for the 14 off-site symbols. The same runs' 499-symbol yfinance breadth batch also ended at 10-12 (`failed_batches=0`). No 429/HTTP/timeout errors were logged.
   - Hypothesis: the yfinance download path published the 10-13 bar late that evening. In the same run, the Yahoo chart endpoint already had the 10-13 close (QQQM 306.16).
   - Not provable from the old logs, because the fallback recorded nothing per request.
4. **Not observed:** the Pages deploy lagging the data commit (each deploy finished ≤2 min after its commit), or a duplicate or lost write. The second run of a session is idempotent: `unchanged`, and conflicts are quarantined.

## 40-symbol OHLCV (do not mix the three layers)
- **Repository history archive:** 40/40 full OHLCV for both 10-13 and 10-14.
  - 26 symbols come from the site data. The 14 (AAOI AAPL CRWV DIA GLD HYG IWM META MU NOW TLT XLE XLF XLK) come from the Yahoo fallback; each passed the 0.5% close-basis guard.
  - IWM, HYG and TLT are complete for 10-13 and 10-14.
- **Homepage quotes:** 26 symbols (the display pool). The 14 are intentionally not displayed.
- **Event inputs:** `macro_event_watch.json` market_as_of 2026-10-14.
- **Later conflicts:** 9 small differences in the 10-14 open price (e.g. GOOG 351.43 → 351.545) were quarantined. The archive was not overwritten.

## This PR (small, Shadow-neutral)
- `local_history_agent.py` now logs every fallback request in `update.fallback_attempts`: requested symbols, returned last date, and HTTP status or error.
- It records `update.basis_check` for each fallback symbol: overlap sessions, max |close diff| %, and the 0.5% tolerance.
- **Second free fallback**, used only for symbols still lacking the expected session: the public Yahoo chart endpoint that `fetch_and_build.py` already uses. No new service and no key.
  - It makes one low-frequency request per symbol and applies the same basis guard.
  - It keeps full OHLC only and never synthesizes a value; a missing bar stays missing (fail-closed).

## Proposal only (needs owner approval; not implemented)
- Move the 21:30Z/00:35Z/12:35Z crons off popular minutes (e.g. :07/:41) and/or add one later Guardian slot. This changes the cron architecture.
