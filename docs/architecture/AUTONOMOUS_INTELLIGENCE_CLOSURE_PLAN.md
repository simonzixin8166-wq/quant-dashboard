# MyAlpha Autonomous Intelligence Closure Plan

Status: active  
Formal website version: V6.9.0  
Program principle: fix defects inline, then automatically return to the active milestone. Defect work must not replace the roadmap.

## North Star

MyAlpha is an autonomous investment research and decision-support agent.

Canonical pipeline:

Collect → Understand → Structure → Validate → Promote → Scan → Decide → Explain → Learn Again

Today Cockpit is the sole formal action outlet. All other modules are evidence, research, diagnostics, or drill-down surfaces.

## Non-negotiable guardrails

- No automatic trading or automatic position sizing.
- Historical/backfill evidence never becomes genuine Forward evidence by relabeling.
- Protected Production Rules cannot be changed by autonomous learning.
- Promotion Gate + Human Approval remain mandatory for protected production changes.
- Missing definitions, ambiguous identity, stale data, or conflicting provenance fail closed.
- A source opinion is never a production signal merely because an author is popular or recently correct.

## Milestone A — Source Reliability

Goal: continuous, attributable, deduplicated collection from Wenxuecity, YouTube, news, SEC/company evidence, market/macro data.

Exit criteria:
- scheduled collection is healthy;
- late/pending recovery exists;
- primary subject vs incidental symbol attribution is explicit;
- content quality is known;
- source identity/timestamp provenance is retained;
- missing transcript/body is visible, not silently treated as learned content.

Current state: substantially operational; YouTube pending recovery and fast daily intake are implemented. Primary-subject attribution remains an active quality item.

## Milestone B — Autonomous Learning Core

Goal: convert source meaning into reusable machine-testable Research/Shadow candidates without bespoke coding for each blogger or method.

Required chain:
Source Intelligence → Source Reading → Candidate Rule Compiler → Candidate Registry

Candidate schema must preserve:
- source_id / proposition_id;
- author/source/published_at;
- primary scope/universe;
- method family;
- trigger / confirmation / invalidation role;
- machine-ready conditions;
- unresolved inputs;
- horizon;
- reproducibility status;
- historical vs genuine-forward evidence role;
- overlap/family identity;
- production_eligible=false by default.

Exit criteria:
- generic candidate compilation passes;
- unknown TCDS/PPO definitions remain unresolved;
- no invented thresholds/formulas/horizons;
- backfill cannot become Forward;
- candidate registry is deterministic and source-attributable.

Current state: ACTIVE.

## Milestone C — Validation and Evidence Maturity

Goal: evaluate candidate methods without look-ahead and without inflating sample size.

Required chain:
Candidate Registry → Historical Replay → Walk-forward → EventScore 5/20/60 → Family comparison → Forward observation → Promotion Gate

Metrics:
- effective N;
- positive rate and excess return vs baseline;
- MAE / MFE;
- regime split;
- contradiction/failure cases;
- author concentration;
- overlap/dedup;
- data/source freshness.

Exit criteria:
- Historical and Forward remain strictly isolated;
- replay is reproducible;
- first genuine Forward rule path observed;
- promotion uses Rule Family, not isolated statements;
- no gate lowering to manufacture maturity.

Current state: engineering mostly present; real Forward maturity still naturally zero.

## Milestone D — Decision Fusion and Full-Watchlist Scan

Goal: combine validated evidence into position-aware decisions across the whole watchlist.

Inputs:
- market regime / breadth / VIX;
- Trend Pulse and price structure;
- direct company / SEC / fundamentals;
- ranked events and news;
- promoted learned-method evidence;
- thesis state;
- actual holding state;
- counter-evidence and uncertainty.

Formal Action vocabulary:
WATCH / EARLY_ENTRY / CONFIRMED_ENTRY / HOLD / NO_ADD / REDUCE / EXIT

Exit criteria:
- every watched symbol is scanned;
- holding vs non-holding changes action semantics;
- every formal action has Why Now, support, counter-evidence, next confirmation, invalidation, confidence, freshness;
- ambiguous labels such as RISK alone are forbidden as final output.

Current state: PARTIAL.

## Milestone E — Single Action Outlet

Goal: user can rely on one page and not miss signals.

Authority:
Today Cockpit = Sole Action Outlet

Rules:
- all valid actions appear on one page;
- no silent top-N truncation of active signals;
- grouped by urgent / entry / hold-no-add / watch-review;
- summary cards navigate to the relevant explanation or action group;
- all secondary pages show evidence only and return to Today Cockpit for formal action.

Exit criteria:
- Autonomous QA enforces sole outlet;
- Daily Update cannot regenerate duplicate static action surfaces;
- desktop/mobile both expose the same complete action set.

Current state: ACTIVE / near closure.

## Development discipline

1. Work only from the active milestone.
2. If a bug appears, classify it as blocker/P1/P2.
3. Fix the bug and add regression coverage.
4. Re-run relevant QA.
5. Automatically return to the active milestone in the same development cycle.
6. Do not start a new isolated feature unless it maps to a milestone exit criterion.
7. Report progress by milestone and remaining gaps, not by a list of edited files.

## Closure definition

Learning Quality closes only when:
- BLOCKER = 0
- P1 = 0
- Source → Candidate → Validation → Forward → Promotion boundary is intact
- Today Cockpit remains the only formal action authority

Empirical 20/60-day maturity cannot be accelerated with synthetic or backfilled samples.
