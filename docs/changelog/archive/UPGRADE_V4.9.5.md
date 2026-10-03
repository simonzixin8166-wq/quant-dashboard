# V4.9.5 — Research Assistant / BrightLine Method Library

## Goal
Turn the Wenxuecity area from an article collection into a plain-language investment research assistant.

## What changed
- Added `投资助手` as the default Wenxuecity tab.
- Curated 9 additional publicly indexed BrightLine articles; embedded research set is now 20 blog posts + 2 forum posts.
- Added 12 reusable BrightLine method cards with:
  - one-sentence plain-language meaning
  - what an ordinary investor should check
  - when to reassess
  - professional metrics with plain Chinese explanations
  - mapping to current myAlphaView modules
- Added `research-methods.js` as a reusable method library. Repeated blogger ideas should merge into one method instead of creating duplicate article cards.
- Added `config/research_inbox.json` so future specific links or pasted article text can enter the same analysis flow.
- Research inbox URL fetch remains restricted to approved Wenxuecity hosts; pasted text works without network access.
- Changed the blog scan schedule from every 6 hours to once daily. Forum close digest remains gated by the NYSE trading calendar.
- Kept all existing core ETF thresholds, Trend Pulse calculations and option math unchanged.

## Research principles
- Blogger views are evidence sources, not trading rules.
- Do not copy personal position sizes or leverage.
- Default UI order: conclusion -> reason -> plain action -> invalidation -> professional details.
- No 100-point strategy score.
- Trend Pulse remains second-layer confirmation, not a standalone buy/sell signal.
