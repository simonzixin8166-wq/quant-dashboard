# V4.9.4 — BrightLine coverage + compact stock scan

- Move anonymous analytics to the true page bottom and visually demote it.
- Make the desktop stock watchlist fit all eight columns without horizontal dragging.
- BrightLine collector now starts from `all.html`, follows archive pagination, prioritizes configured 2026 articles, and records discovered/archive counts.
- Increase one-run article budget to 48 so repeated scheduled runs converge much faster toward 2026 coverage.
- Literature City method view now shows 2026 coverage and automatically merges repeated article themes into method candidates; repeated themes require >=2 supporting articles.
- No source-access bypass: 403/429 still stop collection and old cached research is retained.
