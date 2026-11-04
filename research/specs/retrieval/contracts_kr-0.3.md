# Unified retrieval · pre-implementation contracts kr-0.3 (frozen definitions, no code)

Status: FROZEN DEFINITIONS, NOT IMPLEMENTED. Answers GPT #133 6620702390 §B–E, which asks for contracts to be frozen
**before** implementation. Tests that run these contracts are an implementation deliverable after renewal; none of
this file claims they already pass. Any change to it is a new version (kr-0.4). Learning state UNPROVEN / FINAL=NO.
Read with `design_v0.2.1.md`; where they differ, this file wins.

## 1. Time contract (GPT §B)

### 1.1 Fields
Each time field `F` is stored as `F` (ISO-8601 UTC; date-only values stay `YYYY-MM-DD`), plus `F_raw` (original string),
`F_source` (`<file>#<field>`) and `F_quality`.

| Field | Meaning | Source mapping (current files) | Missing → |
|---|---|---|---|
| `published_at` | when the author or the issuer published it | feed/store `published_at`; SEC `filing_date`; fundamentals `filed` | `unknown` |
| `first_seen_at` | earliest time the system **provably** held the item | store `first_fetched_at`; ledgers `captured_at`; journal `generated_at`; outcomes `scored_at` (for the outcome row itself) | `unknown` → never visible in strict replay |
| `ingested_at` | when the index builder read it | index build time | always set |
| `valid_time` | market date the content is about | `session` / `market_as_of` / `as_of` / `filed` | `unknown` |
| `matures_on` | scheduled maturity date | ledger `matures` / outcome `matures_on` | n/a |
| `outcome_known_at` | when the outcome row was actually written | outcome `scored_at` | `unknown` → outcome never visible in strict replay |

### 1.2 Quality enum (per field, never per record)
| Value | Rule |
|---|---|
| `verified` | written by our own pipeline at that moment (a ledger `captured_at`, a store `first_fetched_at`, an outcome `scored_at`), or an official filing date |
| `inferred` | derived from another verified field by a fixed, documented rule, e.g. a session close computed from `valid_time` |
| `date_only` | the day is known but the time is not, e.g. a store `published_at` with `published_at_semantics=source_archive_publication_date` |
| `unknown` | anything else, including `published_at_semantics=upstream_published_at_unverified` (2,758 store rows) and `missing_published_at` (35) |

**Strict replay at T:**
- An item is visible only if `first_seen_at_quality = verified` and `first_seen_at ≤ T`.
- `inferred` may be shown in exploratory mode, labelled "inferred", and never counts in a blind-test answer.
- `published_at` never decides visibility.
- `first_fetched_at` of initial_migration and backfill rows is the time the store first held them. That is a conservative upper bound, which can only make an item appear later, never earlier.

### 1.3 Versioned outcomes (append-only)
- Each outcome row carries `outcome_id`, `outcome_version` (1, 2, …), `supersedes` (the previous `outcome_id` or null), and `kind` ∈ {`result`, `correction`, `retraction`}.
- Rows are never edited or deleted.
- **Selection at T:**
  1. keep rows with `outcome_known_at_quality = verified` and `outcome_known_at ≤ T`;
  2. within each `event_id`, take the highest `outcome_version` among those rows;
  3. if that row is a `retraction`, report `retracted` and no value.

  Filtering always comes before choosing the latest version, so a later correction can never leak into an earlier T.
- Today `forward_outcomes.jsonl` has one row per event and no corrections. Its index rows get `outcome_version = 1` and `supersedes = null`.

### 1.4 Tests to deliver after renewal (each must exist and pass before any use)
1. T earlier than `first_seen_at` → not visible.
2. T between `first_seen_at` and the outcome → item visible, outcome hidden.
3. T after `matures_on` but before `outcome_known_at` → outcome hidden.
4. Correction written after T1 → at T1 you see v1, at T2 you see v2.
5. Retraction → `retracted`.
6. Unknown or inferred `first_seen_at` → excluded from strict replay.
7. Backfill row whose `published_at` is older than T but whose `first_seen_at` is later than T → not visible.

## 2. State contract (GPT §C)

### 2.1 Enums
| Field | Values |
|---|---|
| `ingestion_mode` | `live`, `backfill`, `initial_migration`, `manual_forward` |
| `temporal_class` | `genuine_forward`, `promoted_forward`, `historical_replay`, `descriptive` |
| `maturity_state` | `not_applicable`, `pending`, `matured_h20`, `matured_h60`, `matured_h120`, `unavailable`, `invalid` |
| `validation_state` | `unvalidated`, `shadow`, `independently_validated` |
| `production_eligibility` | `false` (default), `true` |

### 2.2 Allowed combinations (any combination not listed is rejected at build time with reason `illegal_state_combination`)
| temporal_class | allowed ingestion_mode | allowed maturity_state | allowed validation_state | Evidence required |
|---|---|---|---|---|
| `genuine_forward` | `live` only | pending / matured_* / unavailable / invalid | unvalidated, shadow | ledger row in `forward_observations.jsonl` with `attested_forward=true`, `captured_at` (verified) before the next session open, and `market_as_of = session` |
| `promoted_forward` | `live` only | as above | unvalidated, shadow | row in `forward_observations_promoted.jsonl`; always reported as a separate group, never pooled with genuine |
| `historical_replay` | `backfill`, `initial_migration` | not_applicable, matured_* | unvalidated | replay engine output; must never be shown as forward |
| `descriptive` | any | not_applicable | unvalidated, shadow | everything else (posts, propositions, memories, incidents, SEC text) |

Hard rules:
- `manual_forward` can never be `genuine_forward` or `promoted_forward`. A manual entry is evidence that something was said, not a forward prediction.
- `backfill` and `initial_migration` can never be any `*_forward` class.
- `independently_validated` needs a recorded independent check (blind test or third-party audit) referenced by ID. No file meets this today, so the value is unused.
- `matured_*` describes elapsed time only. It never implies validation.

### 2.3 Production eligibility (fail closed)
- `production_eligibility = true` requires every source-side flag that exists on the row to be true, for example `eligible_for_production` and `scoreable_as_method_performance`.
- Any false, missing or contradictory flag gives `false`, and a `rejection` object `{reason, fields, source_file, source_sha}` is written to the build audit log `research/index/build_audit.jsonl`.
- The index never sets `true` on its own. Today every row is `false`.

### 2.4 Tests to deliver after renewal
- One end-to-end example for each of the four classes, from a real file row to its index row, with every field checked.
- An illegal-combination test for every rejected pair in 2.2.
- A test that manual_forward cannot become genuine.
- A production-eligibility conflict test that checks the audit record.

## 3. Blind-test governance (GPT §D)
- **Authors:**
  - The Owner or GPT writes the frozen blind set: about 100 questions with gold answers (required doc_ids, forbidden future doc_ids, expected abstain code, supporting and opposing sets).
  - Claude, as implementer and tuner, must not see the answers before the scored run.
- **Storage:**
  - Questions and answers are kept outside both repos until the scored run.
  - Only `sha256(questions)` and `sha256(answers)` are committed, in `research/specs/retrieval/blind_set_hashes.json`, with the freeze time and version.
  - At scoring time the files are revealed and their hashes must match.
- **Sets:**
  - Smoke set: the 25 questions in the design, public, run on every change.
  - Development set: about 60 questions, public.
  - Frozen blind set: the about 100 questions above.
  
  A question may appear in only one set, enforced by checking question-text hashes across the sets.
- **Reported separately (never folded into one number):**
  - fact accuracy (the primary metric), with Wilson 95% interval;
  - citation support rate;
  - time legality rate;
  - correct-abstain rate;
  - wrong-abstain rate.

  Each has its denominator, per category and overall.
- **Zero tolerance:** one time-travel, privacy-leak or fabricated-citation case fails the run. The test cases for these three are written before the blind run and kept in the repo with their logs.
- **Wording:** a pass on about 100 questions is an "initial offline acceptance". It says nothing about long-term accuracy or about whether any investment method works.

## 4. Privacy and isolation (GPT §E)

### 4.1 Allowlist
Only these index fields may hold content:
- `doc_id`, `kind`, `symbols`, `primary_symbol`
- `author`, `source_type`, `url`
- the time fields in §1 and their `_raw`, `_source` and `_quality` companions
- the four state fields in §2 and `production_eligibility`
- `stance`, `decision`, `outcome`, `excess_vs_qqq`
- `title`, `excerpt` (≤ 360 chars), `propositions`, `opposing`, `invalidation`
- `content_sha`, `source_file`, `source_commit`
- `duplicate_group_id`, `duplicate_level`, `links`
- `data_classification`, `visibility`, `origin_repo`, `redaction_status`

Any other key, or any source file not on the source allowlist (the inventory list minus EXCLUDED), fails the build. Fields are never silently dropped.

### 4.2 Hard exclusions
Every one of these fails the build:
- the `myalpha-ledger-private` repo, Supabase, and the browser journal;
- any field named like `position`, `qty`, `shares`, `amount`, `cost`, `account`, `pnl`, `premium_paid`, `strike_owned`.

### 4.3 Canary and scan
- **Canary fixtures:** fake account numbers, position tables, option holdings, dollar amounts, a private note and a private URL are planted in a test source.
- **Scanned:** the index JSONL, build logs, error messages, Actions artifacts, and the Pages build output.
- **Result:** any canary hit fails the build. It is an error, never a warning.

### 4.4 Isolation from production
A dependency check (a test) scans every production script and workflow — Daily, Guardian, Server Action, research-close and QA — and fails if any of them reads `research/index/` or imports the query tool. The index and query tool run only in a separate research-only job.

### 4.5 Anonymous access
The index lives in the repo only. It is never written under `docs/`, so Pages never serves it.

## 5. What is allowed now vs after renewal
| Now (allowed by GPT 6620702390 §F) | After renewal |
|---|---|
| read-only inventory; this contract; an isolated BM25 prototype | implement the index, the query tool and every test listed above; the blind run with the Owner or GPT as question setter |

Not allowed at any stage before a blind PASS and Owner approval:
- production retrieval;
- `past_cases` writes;
- any strategy, threshold or position effect;
- promotion of shadow or promoted methods;
- a web entry;
- private data in a public index;
- paid APIs;
- automatic trading.
