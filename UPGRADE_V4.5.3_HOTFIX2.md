# V4.5.3 Hotfix 2

- Fixes the prior `TypeError: unhashable type: 'dict'` in Trend Pulse rendering.
- Makes `scripts/fetch_and_build.py` self-clean legacy PWA artifacts on every successful website build:
  - `docs/sw.js`
  - `docs/manifest.webmanifest`
  - `docs/offline.html`
  - `docs/assets/pwa.js`
  - legacy PWA install icons
- Keeps responsive mobile web (`mobile-shell.css/js`) intact.
- Prevents `tests/test_build_contract.py` from failing when upgrading by replacing only `fetch_and_build.py` in a repository that still contains older PWA files.
