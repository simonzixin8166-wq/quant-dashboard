# Private Ledger Bootstrap

Target private repository:

`simonzixin8166-wq/myalpha-ledger-private`

The public `quant-dashboard` repository must never contain raw Forward Ledger, Outcome Ledger, Discipline Ledger, Audit Ledger, or private account records.

## Required one-time setup

1. Create a new GitHub repository named `myalpha-ledger-private`.
2. Set visibility to **Private**.
3. Initialize it with a README so branch `main` exists.
4. Create a fine-grained personal access token that can write repository contents for this repository only.
5. Add that token to `quant-dashboard` Actions secrets as:
   - `MYALPHA_LEDGER_TOKEN`

The repository name is intentionally fixed in `.github/workflows/daily.yml`; no repo-name secret is required.

## Forward Clock start behavior

Until the token exists, production remains:

- `mode=observe_only`
- `forward_clock_active=false`
- `storage.reason=missing_token`

On the first successful Daily run after the private repository and token are available:

- the current Playbook states become the Forward baseline;
- current states are **not** backfilled as historical Forward triggers;
- an append-only `forward_clock_started` audit event is written;
- baseline audit records are written for each current Playbook entity;
- public `ledger_anchor.json` publishes only the chain head/hash metadata.

## Safety

- Raw ledger data never enters `docs/`.
- If private ledger write fails, the website still updates.
- A failed write is surfaced as `ledger_write_failed`.
- The failed event is not counted as a valid Forward sample.
- Existing ledger records are never rewritten.
- Corrections are append-only.
