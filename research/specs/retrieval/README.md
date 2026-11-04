# Unified retrieval · design and inventory evidence (kr-0.2.1)

Status: DESIGNED ONLY + read-only inventory. No production code reads anything in this folder. Learning state UNPROVEN / FINAL=NO.
Reviews: #133 6594443196 (v0.1) → 6594478717 (GPT) → 6594524162 (v0.2) → 6594555129 (GPT) → 6620532060 (v0.2.1) → 6620593762 (GPT).

| File | sha256 |
|---|---|
| design_v0.2.1.md (v0.2 + the v0.2.1 section at the end) | `625868078a3c6c562fd8287dbb6aee40cb4080ebee5051d4a008d8201858a6ce` |
| inventory_manifest.json | `3bbb660fa61affcaf7b1b20e0154dbd821d5db5e47c678797185cf31f7b67531` |
| ../../../scripts/retrieval_inventory.py (script `kr-inventory-0.2.1`) | `3047df8d25124a737531a2c87bc3116e813f80d2a072ea794cc19e5068d18b89` |

## Reproduce the manifest
```
git -C quant-dashboard checkout 8ae72dfb30a079b3790258cb59f0fdc36cf9c14b
git -C wxc-bot checkout f54bd0a7c8408de02cce5638cd6c870b7365ac45
# take scripts/retrieval_inventory.py from this branch
python3.11 scripts/retrieval_inventory.py --qd quant-dashboard --wx wxc-bot --out /tmp/inventory_manifest.json
```
Every number except `generated_at` must match `inventory_manifest.json`. The manifest records each input file's sha256
(`sources[].file_sha256`, `directories[].files_sha256`), both commits, and the script's own sha256.

## What the manifest reconciles
- feed vs store, ID by ID: 2,978 = 2,863 − 3 + 118 (`reconciliation.feed_vs_store`, with the full ID lists).
- store vs reading: orphans and store records without a reading record.
- forward outcomes vs observations: orphan outcomes; group / h / status. As of these commits all 106 outcomes are
  promoted / h20 / matured, and genuine_forward outcomes = 0.
- one-to-many: fundamental observations → outcomes; propositions per source.
- duplicate ID rows per source, time-field coverage per source, `replayable` (has an ID and at least one time field).

Excluded by Owner decision (6594477482): the private ledger repo, Supabase tables, browser journal.
