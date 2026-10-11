# MyAlpha knowledge contract v1 (M2, #133 6107376896 / 6109126287)

One append-only ledger, `research/knowledge/shadow_research_cases.jsonl`, links the existing layers
instead of creating a parallel database:

| layer | existing asset it points to | key |
|---|---|---|
| source fact | wxc-bot `state/research_feed.json` record | `source_ref.record_id` + `text_sha256` (+ ≤40-char locator) |
| author claim | claims gold / ce-5 shadow extraction | `author_claims[]` (stance, status, instrument, holder=author) |
| market / official evidence | `data/history/stooq_watchlist.zip`, `docs/data.json` (trend_pulse), `docs/research/auto_thesis_drafts.json` (SEC) | `evidence[]` with `source`, `as_of`, `value` |
| MyAlpha hypothesis | this ledger (shadow) | `case_id`, `myalpha_view` |
| outcome / review | forward observation engine horizons (20 NYSE sessions) | `review.next_review`, `review.invalidation[]` |

## Case record (all fields required; empty lists must be explicit)

- `case_id`, `contract_version`, `created_at`, `analyst` (who drafted; "rule" parts are computed)
- `symbol`, `sources[]` — `{record_id, author, url, published_at, provenance, text_sha256, locator}`
- `author_claims[]` — `{source, stance, status, instrument, holder:"author", quote_locator}`
- `claim_checks[]` — compatibility of each verifiable author statement with market data:
  `{claim, check, data_source, data_as_of, observed, result: compatible | incompatible | unverifiable}`.
  **A compatible price check never proves a trade happened** (no broker confirmation) — wording must say
  "compatible with market data", never "verified execution".
- `evidence[]` — `{name, value, source, as_of}` (price, moving averages, trend pulse, VIX, filings…)
- `myalpha_view` — `{stance: bullish | neutral | bearish | cannot_judge, basis: "rule"|"analyst", summary,
  agrees_with_author: true|false|partial|n/a}`; must not merely restate the author.
- `supporting[]`, `opposing[]` — evidence for and against the view (each item cites an `evidence` name)
- `applies_when[]`, `invalidation[]` — machine-checkable `{metric, op, value, note}` where possible
- `unknowns[]` — what is missing (no trade proof, no valuation data, filings not extracted…)
- `review` — `{next_review (date), horizon_sessions, status: active | invalidated | expired | abstained}`
- `shadow: true`, `production_use: false` — cases never feed scoring, Forward or recommendations

Abstention is a valid case: `myalpha_view.stance = cannot_judge` with the missing evidence listed.
Records are append-only; a revision is a new record with `supersedes: <case_id>`.
