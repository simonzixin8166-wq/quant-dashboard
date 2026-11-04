# Unified retrieval · design and inventory evidence (kr-0.2.1)

Status: DESIGNED ONLY + read-only inventory. No production code reads anything in this folder. Learning state UNPROVEN / FINAL=NO.
Reviews: #133 6594443196 (v0.1) → 6594478717 (GPT) → 6594524162 (v0.2) → 6594555129 (GPT) → 6620532060 (v0.2.1) → 6620593762 (GPT) → 6620639342 → 6620702390 (GPT).

| File | Role | sha256 |
|---|---|---|
| `design_v0.2.1.md` | design. §2 holds the current counts; numbers in the older #133 comments are void | `4e1c3f091109fb55b7d726eb21f652f035c80ffb2e8f234e9c9346e5c96287f5` |
| `inventory_manifest.json` | **the only authoritative counts** | `3bbb660fa61affcaf7b1b20e0154dbd821d5db5e47c678797185cf31f7b67531` |
| `scripts/retrieval_inventory.py` | read-only generator (`kr-inventory-0.2.1`) | `3047df8d25124a737531a2c87bc3116e813f80d2a072ea794cc19e5068d18b89` |
| `tests/check_retrieval_inventory.py` | recompute and field-by-field comparison | `79f97c77d2c482c1483e8b71ba41414186b712293a3d0a043a0bc50544eefadd` |
| `.github/workflows/retrieval-inventory-check.yml` | CI gate: fails on any difference except `generated_at` | — |

Pinned inputs (also inside the manifest under `commits`):
- quant-dashboard `8ae72dfb30a079b3790258cb59f0fdc36cf9c14b`
- wxc-bot `f54bd0a7c8408de02cce5638cd6c870b7365ac45`

## Reproduce from a clean machine
Requirements: git, Python 3.11 (standard library only, no pip packages), network access to github.com. Both repos are public.
```bash
mkdir retrieval-check && cd retrieval-check                      # every command below runs in this directory
git clone https://github.com/simonzixin8166-wq/quant-dashboard.git pr
git -C pr checkout main                                           # after this PR merges (before: branch specs/retrieval-recompute-gate)
git clone https://github.com/simonzixin8166-wq/quant-dashboard.git qd
git -C qd checkout 8ae72dfb30a079b3790258cb59f0fdc36cf9c14b       # pinned input, detached HEAD
git clone https://github.com/simonzixin8166-wq/wxc-bot.git wx
git -C wx checkout f54bd0a7c8408de02cce5638cd6c870b7365ac45       # pinned input, detached HEAD
python3.11 --version                                              # expect 3.11.x
sha256sum pr/research/specs/retrieval/inventory_manifest.json pr/scripts/retrieval_inventory.py   # compare with the table above
python3.11 pr/tests/check_retrieval_inventory.py --qd qd --wx wx  # prints an audit record; exit 0 = PASS, 1 = FAIL
# optional: regenerate the manifest yourself and diff it by hand
python3.11 pr/scripts/retrieval_inventory.py --qd qd --wx wx --out manifest_recomputed.json
```
The check prints the commits it actually read, the script sha256, the manifest sha256, the Python version, the run time,
a MATCH/DIFF per top-level field and every differing path. A tampered manifest (for example propositions set back to 7,129)
fails with `DIFF reconciliation.store_vs_reading.propositions: manifest=7129 recomputed=7136`.

## What the manifest reconciles
- feed vs store, ID by ID: 2,978 = 2,863 − 3 + 118 (`reconciliation.feed_vs_store`, with both ID lists).
- store vs reading: orphans and store records without a reading record; propositions 7,136.
- forward outcomes vs observations: orphan outcomes, group / h / status. All 106 outcomes are promoted / h20 / matured;
  genuine_forward outcomes = 0. Promoted results must never be called genuine forward.
- one-to-many (fundamental observations → outcomes), duplicate ID rows, time-field coverage, `replayable` per source,
  and the sha256 of every input file and of every file in the listed directories.

Excluded by Owner decision (6594477482): the private ledger repo, Supabase tables and the browser journal.
