# V6.15 Step 0 Findings

Date: 2026-10-04  
Baseline main: `841f2e036c870949f9b1b4dc795d664bf40bc603`  
Scope: read-only investigation. No production or research logic changed.

## 1. `published_at` semantics

### BrightLine / Wenxuecity blog archive
`source_intelligence_engine.seed_brightline()` maps the archive field `article.date` directly to `published_at`.
For this source type, `published_at` is therefore a source/archive publication date.

### Upstream feed records
The engine preserves the upstream `published_at` field but does not separately persist a `fetched_at` timestamp in the normalized record.
Therefore the repository cannot currently prove, for every upstream source type, whether the field is a true publication timestamp or a collection timestamp.

**V6.15 policy:** verified publication timestamps may anchor an event. Unverified or missing timestamps must remain non-scoreable until persistent storage records `first_fetched_at`; after that they may use `first_fetched_at` only as a conservative start point.

## 2. 800-record truncation

Current normalized source count is 1,215, while the public source record array contains at most 800 rows.

Two independent hard limits exist:

- `source_intelligence_engine.py`: `records = rows[:800]`
- `source_reading_memory.py`: `records = memories[:800]`

In addition, `operation_cases` has its own `[:120]` limit.

**Conclusion:** 800 is not a natural dataset size. It is a display/storage window. It must not be used as the long-term evaluation universe.

## 3. `records.operations` vs `operation_cases.operations`

Both arrays are produced from the same normalized `rows` object in the same build, so overlapping records should carry the same operation content. However:

- the two arrays are independently truncated;
- the current pipeline has no content-hash assertion;
- downstream code uses positional `operation_index` as part of event identity.

**V6.15.1 requirement:** compare canonical operation-content hashes for every overlapping record and fail the research build on a mismatch; Rule Registry identity must not depend on operation position.

## Step 0 disposition

Step 0 is complete enough to proceed to V6.15.0, with the following constraints carried forward:

1. upstream feed timestamp semantics remain explicitly unverified until persisted provenance is available;
2. the 800-row window is presentation/storage only;
3. operation-list consistency becomes an enforced invariant in V6.15.1;
4. no Step 0 finding has been silently repaired in this investigation commit.
