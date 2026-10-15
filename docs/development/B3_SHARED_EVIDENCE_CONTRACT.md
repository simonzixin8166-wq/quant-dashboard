# B3-01 — Shared evidence contract (read-only minimal design, not implemented)

Status: **design only** (#133, owner instruction 2026-10-15 06:07Z). No code, ledger, cron or consumer changes in this step.
Gate for implementation: B4-03 evidence passes (`research/audit/sec_v2_migration_audit.json` gate blockers = 0 and one real
trading day repeats it) **and** the P0 core chain is stable. Learning stays UNPROVEN / FINAL=NO.

## 1. Problem (from the real artifacts, 2026-10-15)

| stream | file | evidence today | ledger |
|---|---|---|---|
| Auto Research (rule engine) | `research/knowledge/auto_research_journal.jsonl` | structured items `{name, group, value, sign, source, as_of}` + `inputs{source, as_of, sha256}` + B1/B2 `experience_basis` (#250) | append-only, revisited, maturity-scored |
| V6 planner / executor | `docs/research/research_execution.json` | **free-text strings** (`supporting_evidence[]`, `counter_evidence[]`, `unknowns[]`), no as_of, no source path, no hash | overwritten each run (`analysis_runs`, `last_analyzed_at`), not append-only |
| Knowledge cases (M2) | `research/knowledge/shadow_research_cases.jsonl` | `evidence[] {name, value, source, as_of}` | append-only |

The two judgment streams cannot cite the same fact: nothing links "NBIS 60-session precedent median 1.8%" (V6 string)
to the journal's `precedents` entry, and V6 strings carry no as_of, so their timing cannot be checked.

## 2. Contract `evidence-1` (one item = one fact as known at a time)

| field | rule |
|---|---|
| `evidence_id` | `sha256(kind|symbol|source|source_key|as_of|canonical value)[:16]` — deterministic, so both streams compute the same id for the same fact |
| `kind` | `price_trend`, `macro`, `sec_fact`, `event`, `precedent`, `error_attribution`, `historical_reliability`, `author_claim`, `peer` |
| `symbol`, `source`, `source_key` | file path / URL + locator (e.g. `docs/research/sec_fundamentals.json#AMZN.revenue_q`); never third-party full text |
| `as_of` | the data date of the fact; **`unavailable` if the producer does not know it — never filled with the run date** |
| `available_at` | first time the fact was knowable (filing date, vintage, bar close) — look-ahead guard |
| `generated_at`, `producer`, `producer_version` | who wrote it and when |
| `quality` | `ok`, `stale`, `unverified`, `anomaly_review`, `experimental_unvalidated` (author claims) |
| `value_sha256` | hash of the canonical value |
| `stream` | `auto_research` / `v6_executor` / `knowledge_case` |
| `used_in_decision` | always `false` in Shadow |

Rules: ledgers stay separate (no merge, no summed "learning score"); a stream *cites* `evidence_id`s; an item is
admissible for a record only if `available_at ≤` the record's lock time; same-session regenerations reuse ids, so they
never inflate n.

## 3. Minimal implementation plan (after the gate; each a small PR)

1. **Shadow dual-read adapter (read-only):** `scripts/evidence_contract_dual_read.py` maps the journal's structured
   evidence and `inputs` to `evidence-1` items, and maps V6 strings only where a structured source exists
   (e.g. SEC filing date → `sec_fact`); unmappable V6 strings are reported as `unstructured` with `as_of=unavailable`.
   Output `docs/research/shadow/evidence_contract_dual_read.json`: items per stream, shared ids, unmapped counts.
   Tests: determinism, no look-ahead (`available_at > lock` rejected), same-session dedupe, unavailable never defaulted.
2. **V6 executor emits structured evidence alongside its strings** (additive field, strings unchanged), so the overlap
   can grow from real data rather than parsing.
3. **Regression gate:** both streams' existing outputs byte-identical apart from the new fields; module manifest
   reports the shared-id overlap from the real artifact.

## 4. Not in scope

No change to stances, scores, thresholds, cron, private positions, Forward tracks; no LLM calls; no new paid data.
No automatic promotion of any Shadow result.
