# Unified retrieval · pre-implementation contracts kr-0.3.1 (frozen definitions)

Status: FROZEN DEFINITIONS, NOT IMPLEMENTED. Answers GPT #133 6620702390 §B–E, which asks for contracts to be frozen
**before** implementation. Tests that run these contracts are an implementation deliverable after renewal; none of
this file claims they already pass. Any change to it is a new version (kr-0.4). Learning state UNPROVEN / FINAL=NO.
Read with `design_v0.2.1.md`; where they differ, this file wins.

kr-0.3.1 (GPT #133 6620929885) changes only §2.3, §3 and §4. §1 was judged PASS and is unchanged byte for byte.
Machine-readable parts: `eligibility_contract.json`, `blind_hash_spec.json`, `source_admission.json`. Executable checks:
`tests/test_retrieval_contracts.py` (reference functions over frozen fixtures) and `tests/test_retrieval_isolation.py`
(the production entry gate, which runs today). The future index implementation must pass the same fixtures.

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

### 2.3 Production eligibility (fail closed) — required flags per source kind
Machine-readable: `eligibility_contract.json` (19 kinds, 37 fixtures).

`production_eligibility = true` only if **all** of the following hold:
1. the kind is approval-capable;
2. every required flag is present, non-null, of the expected type and equal to the expected value;
3. no conflict rule fires;
4. `owner_production_approval_id` is a non-empty string. No row has this field today.

Otherwise the result is `false` with exactly one reason code. The first match in this order wins:
`type_never_eligible` → `missing_flag` → `null_flag` → `unknown_value` → `flag_conflict` → `value_mismatch` → `no_owner_approval`.
The flags that actually exist on a row are never used to infer eligibility on their own.

| Kind | Approval-capable | Required flags (exact values) | Conflict rules |
|---|---|---|---|
| forward_observation | yes | `attested_forward = true` | `market_as_of ≠ session` |
| forward_outcome | yes | `eligible = true`, `status = "matured"` | `eligible = true` while `status ≠ matured`; `group ≠ genuine_forward` |
| rule (`source_rule_lifecycle`) | yes | `eligible_for_production = true`, `scoreable_as_method_performance = true` | eligible = true while scoreable = false |
| auto_research | yes | `production_use = true`, `shadow = false` | production_use = true while shadow = true |
| shadow_case | yes | `production_use = true`, `shadow = false` | as above |
| forward_observation_promoted, source_post, proposition, sec_filing, fundamental_outcome, event_outcome, market_state_outcome, macro_observation, source_outcome_validation, contradiction, method_memory, situation_memory, historical_replay, incident; any unregistered kind | **never** | — | — |

Every rejection writes `{reason, kind, fields, source_file, source_sha}` to `research/index/build_audit.jsonl`.

Fixtures cover, for each approval-capable kind, a legal row, a missing flag and a conflict. Some kinds also have null, unknown-value, no-approval and current-reality rows (current real rows are false with `value_mismatch`). Each never-eligible kind has one row.

### 2.4 Tests to deliver after renewal
- One end-to-end example for each of the four classes, from a real file row to its index row, with every field checked.
- An illegal-combination test for every rejected pair in 2.2.
- A test that manual_forward cannot become genuine.
- A production-eligibility conflict test that checks the audit record.

## 3. Blind-test governance (GPT §D)
- **Authors:**
  - The Owner or GPT writes the frozen blind set: about 100 questions with gold answers. Each answer lists the required doc_ids, the forbidden future doc_ids, the expected abstain code, and the supporting and opposing sets.
  - Claude, as implementer and tuner, does not see the answers before the scored run.
- **Storage:** questions and answers stay outside both repos until the scored run. Only their two hashes, the freeze time and the version are committed, in `research/specs/retrieval/blind_set_hashes.json`. At scoring time both files are revealed and must reproduce the hashes.
- **Canonical form for hashing** (machine-readable, with a worked example and hashes: `blind_hash_spec.json`):
  1. UTF-8; every string Unicode NFC; CRLF and CR become LF; no other whitespace change inside strings.
  2. One JSON array per file, sorted by `question_id` (string ascending). Arrays inside an object keep their authored order.
  3. `json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`, with no trailing newline.
  4. SHA-256, lowercase hex.
  5. Questions and answers are two separate files with two separate hashes. The question file carries no answer fields.

  `tests/test_retrieval_contracts.py` checks that the example hashes reproduce, that the hash does not change with item order, CRLF or NFC/NFD, and that it does change when a single space is added.
- **Sets:** the smoke set (the 25 design questions), the development set (about 60) and the frozen blind set (about 100) are disjoint. This is checked by comparing hashes of each question's canonical `text` across the sets.
- **Metrics**, for Q = all frozen blind questions, reported separately per category and overall, each with its numerator, denominator and a Wilson 95% interval:

| Metric | Numerator | Denominator |
|---|---|---|
| factual accuracy (primary) | questions judged correct: every cited doc_id exists, is time-legal and supports the stated answer; or, where the gold answer is abstain, the system abstains with the gold reason code | \|Q\| |
| citation support rate | citations that exist, are time-legal and support the claim they are attached to | all citations emitted across Q (reported as "n/a, 0 citations" if none) |
| temporal legality | questions whose answer cites no record that was invisible at the question's `as_of` | \|Q\| (must equal 1.0) |
| correct-abstention rate | gold = abstain, and the system abstains with the gold reason code | questions with gold = abstain |
| incorrect-abstention rate | gold = answer, and the system abstains or returns nothing | questions with gold = answer |

- **Missing output:** a timeout, crash or empty output on a question counts as incorrect for factual accuracy. If the gold answer is "answer", it counts as an incorrect abstention; if the gold answer is "abstain", it does not count as a correct abstention.
- **Exclusions:** a question may be excluded only if the Owner invalidated it before scoring and recorded a reason. Exclusions are listed and capped at 5% of Q. A question is never excluded because the system failed it.
- **Zero tolerance:** one time-travel, privacy-leak or fabricated-citation case fails the run, whatever the totals. The test cases for these three are written and committed before the blind run.
- **Wording:** a pass on about 100 questions is an "initial offline acceptance". It is not evidence of long-term accuracy or of whether any investment method works.

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

### 4.1a Source admission (fail closed)
Machine-readable: `source_admission.json`.
- A source enters the index only if its class is `public` (our own pipeline output, already public) or `research-safe` (public-repo content that carries third-party titles, ≤ 360-character excerpts or extracted claims, admitted under the no-full-text rule).
- `excluded`, any other value, a missing entry, or a source not listed is rejected and fails the build. Appearing in the inventory manifest does **not** admit a source.
- Every inventory source is classified today. The test asserts this and rejects unknown names.

### 4.2 Hard exclusions
Every one of these fails the build:
- the `myalpha-ledger-private` repo, Supabase, and the browser journal;
- any field named like `position`, `qty`, `shares`, `amount`, `cost`, `account`, `pnl`, `premium_paid`, `strike_owned`.

### 4.3 Canary and scan (values, not only field names)
- **Canary fixtures:** a test source carries planted values, both at the top level and nested inside objects and arrays:
  - a fake account number, a position table, an option holding and dollar amounts;
  - a private note, a private Supabase URL and a private-ledger repo URL;
  - unique `CANARY-<uuid>` tokens.
- **What the scanner checks:** it walks every value recursively, not only field names. It matches the canary tokens; account-like digit runs; `$`/USD amounts next to position words (股 / shares / contracts / 持仓); e-mail addresses; and the private URLs.
- **Where it scans:**
  - the index JSONL, excerpts, propositions, claims and URLs;
  - the build log and error messages;
  - Actions artifacts;
  - the Pages build output (`docs/`).
- **Result:** any hit is an error that blocks the build or publish. It is never downgraded to a warning.
- **Status:** implemented after renewal, together with the index.

### 4.4 Isolation from production — runs today
`tests/test_retrieval_isolation.py` builds the full production entry list and fails if any entry contains `research/index`, `blind_set`, `knowledge_index`, `knowledge_query` or `retrieval_index`. The list covers:
- every GitHub Actions workflow except the research-only `retrieval-inventory-check.yml`, including Daily, Guardian, Server Action Watch, QA, research-close triggers and deploy-supabase;
- every script those workflows run, plus their local imports, followed transitively;
- every Pages HTML and JS file;
- every Supabase function and migration.

The snapshot list, with a sha256 per file, is in `production_entry_list.json` (counts are in the file; 0 hits at this commit). The two retrieval checkers are excluded by name because they spell out the forbidden paths..

A negative test was run: planting the string `research/index` into `scripts/daily_skip_gate.py` makes the gate fail. Any hit is an error that blocks, never a warning.

The gate runs in `v56-pr-validation`, so every PR is checked.

wxc-bot is out of scope: it never reads quant-dashboard files.

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

## 6. kr-0.3.2 delta (GPT #133 6621145320: B2, C3, D2, D3, D4 only; §1 unchanged byte for byte)

- **§2.3 → B2 executable rejection audit.** `scripts/retrieval_eligibility.py` evaluates every row with the frozen
  reason order of `eligibility_contract.json` and writes rejections to an append-only audit log (`open('a')`; a record
  missing reason / kind / fields / source_file / source_sha is refused). The audit path is supplied by the caller; the
  module hardcodes no index path. Test: `tests/test_retrieval_eligibility_audit.py` (real repo rows, append-only prefix
  hash, all 7 reason codes, incomplete records refused).
- **§3 → C3 question-set isolation.** `research/specs/retrieval/question_sets/` holds smoke (26, watchlist symbols
  only) and development (empty) sets without answer fields. The blind set is represented only by
  `blind_set_hashes.json` and stays **BLOCKED** until the Owner/GPT authors and freezes it outside the repo. Test:
  `tests/test_question_set_isolation.py` (id + canonical-text-hash disjointness, planted blind-answer files by name and
  by content are found).
- **§4.4 → D2 isolation gate hardened.** Shell indirection (`bash/sh/source/./x.sh`, `python -m`, `python -c`), string
  literals naming `scripts/*.py`, concatenated / `os.path.join` / `Path` pieces, unreviewed dynamic-import sites
  (`dynamic_import_review.json`: file + line + line sha256) and any `make` target all fail the gate. Test:
  `tests/test_retrieval_isolation_negative.py` (8 evasions planted into real entries, then restored byte for byte).
  `privacy-canary-gate.yml` is research-only (it reads `research/index` only to scan it).
- **§4.3 → D3/D4 recursive scanner and blocking gate.** `scripts/privacy_canary_scan.py` walks every JSON/JSONL value
  and every text line; reports location, category and a redacted snippet only; exit 1 on any hit. Exact-value
  allowlist `privacy_allowlist.json` (sha256 only) is honoured only for entries with `owner_approval`.
  `.github/workflows/privacy-canary-gate.yml` scans `docs/`, `research/specs/retrieval`, `research/index` (if present)
  and its own log, and a second job proves a planted canary exits 1.

### 6.1 Boundaries of static scanning (not a runtime proof)
- The isolation gate is a static, over-approximating text scan. It does not prove runtime behaviour: a path built
  from runtime data (environment variables, network input, file contents) is not visible to it; that is why every
  non-literal dynamic import / exec / eval site must be reviewed by hand and pinned by line hash.
- The privacy scanner is pattern-based. It finds the listed categories; it cannot prove that no other private value
  exists (e.g. a holding written only in prose without quantity and amount). Passing it is necessary, not sufficient.
- Neither gate inspects GitHub artifacts uploaded by other workflows or third-party services.

### 6.2 kr-0.3.2 round 2 (GPT #133 6624784358)
- **B2 approvals.** A non-empty `owner_production_approval_id` is no longer enough. The id must name an `active`
  entry of `owner_approval_registry.json` whose scope is `retrieval_production_eligibility` and whose `kinds` include
  the row's kind. Forged, unknown, revoked, wrong-scope and wrong-kind ids are rejected (`no_owner_approval`). The
  registry holds no retrieval approval today, so every row stays rejected. The reason order now lives only in
  `eligibility_contract.json#reason_order`; `evaluate()` runs one check per listed reason and refuses to run if the two
  differ. Every registry approval must point to an Owner comment on #133 containing its marker;
  `scripts/verify_owner_approvals.py` checks this in CI with the read-only token and fails closed on any error.
- **C3.** Still BLOCKED until the Owner / GPT author and freeze the blind set outside the repo; Claude does not see
  questions or answers. Leak detection now reads every UTF-8 file (Markdown, text, YAML, code, logs, JSON/JSONL) and,
  once per-answer hashes are committed, any line whose canonical hash equals a blind answer.
- **D2.** `privacy-canary-gate.yml` is a `security_qa_only_workflow`, pinned by sha256 in `isolation_exclusions.json`
  and checked to stay read-only (no write permission, no secret except the read-only token, no upload / push / deploy).
  `tests/test_retrieval_isolation_negative.py` is pinned the same way. Dynamic imports pin the helper line, every call
  site, every argument-source line and the resolved targets; an unpinned call, a changed argument line, a reassigned
  path variable or a call of an `unused` helper fails. Static boundaries are listed in `dynamic_import_review.json`.
- **D3.** Output is file + location + category only. Every UTF-8 file is scanned regardless of suffix; ZIP archives are
  unpacked recursively; unreadable / undecodable files, broken archives and missing paths fail as `unscannable`;
  images / fonts / PDF must be pinned by sha256 in `privacy_binary_review.json` after a person looked at them.
  New category `position_quantity` (first-person / account holding with a share or contract count, no amount needed).
  The allowlist needs an exact schema and a matching active `privacy_allowlist` approval; it silences only its own
  category and value.
- **D4.** The same scanner runs as a publish guard (`--staged`: exactly what the next commit would publish) right
  before `git commit` in every workflow that pushes, and before artifact uploads where it can apply. A hit or a
  scanner error stops the push / upload. `privacy-canary-gate.yml` proves each path is blocked by a planted canary.
  Coverage and the workflows that are not covered yet are listed in the PR and in #133.
