# MyAlpha View — product charter (owner-confirmed 2026-10-11; governs every change)

Every code change in this repo and in `wxc-bot` must serve this goal. If a change does not move one of the
four measures below, or breaks a principle, do not make it.

## Goal
A personal **AI investment research assistant**, not an automated trading system. Every day, in the
background and without the owner logging in or Claude writing analysis by hand, MyAlpha collects
information, checks its quality and timing, understands facts and other people's views, forms its own
explainable and falsifiable research judgments, records them append-only, re-checks them daily, scores
them when they mature, and turns verified results into reusable experience. **The owner decides and
places every order manually.**

The owner is a long-term investor: QQQM / VGT index core, QLD risk-balanced, stocks and options auxiliary.
MyAlpha protects the core discipline (DCA, staged gold buying reminders), flags risk early, and gives
evidence-based research hints on stocks and options. It never changes the owner's strategy on its own.

## The four measures (report them with denominators; never substitute feature counts)
1. Does it understand information correctly? (precision / recall / abstention on frozen, unseen tests)
2. How many independent, evidence-based judgments does it form? (not restating authors; abstain when unsure)
3. How much verified experience has it accumulated? (only matured 20/60/120 NYSE-session outcomes count)
4. Is it becoming more reliable over time? (trends + error attribution)

## Principles (non-negotiable)
- Trustworthy, traceable data: source, as_of, first_seen, hashes; missing data → explicit `unavailable`.
- Zero new paid APIs / data / services unless the owner approves in advance.
- No long-term storage of third-party full text; runtime use + short locators + hashes only.
- No automatic orders, no broker order API, no changes to production thresholds or the owner's allocation.
- Private positions stay private and per account; never merged, never published.
- Unverified claims stay shadow (`production_use=false`); author self-reported trades are only
  "compatible with market data", never "verified".
- Historical reconstruction ≠ genuine forward; dev set ≠ frozen test; engineering QA PASS ≠ learning PASS.
- Learning stays **UNPROVEN / FINAL=NO** until matured outcomes and reliable understanding prove otherwise.

## Working rules
- Small PRs → CI → merge → production verification; report progress on Issue #133 with PR / SHA /
  Actions run / evidence. Reuse existing pipelines (Daily, research-close, Guardian, QA) before adding new ones.
- The long-term plan is #133 comment 6107376896 (milestones M1–M4); latest execution orders follow it.
