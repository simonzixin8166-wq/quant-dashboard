# myAlphaView Brand System

## Official brand
- Primary brand: **myAlphaView**
- Product descriptor: **Market Intelligence**
- Chinese descriptor: **投资研究与市场情报平台**
- Domain: **myalphaview.com**

## Visual direction (current)
- Base: deep navy (`--nav` / `--nav2`) sidebar, warm off-white (`--bg`) content area
- Primary accent: brass/gold (`--brass`) — used for the logo mark, active nav state, the dark "Strategy Engine" panel highlights
- Positive: restrained green (`--green`)
- Negative: restrained red (`--red`) — kept visually distinct from the brass brand accent so "brand emphasis" and "market down/alert" are never confused
- No indigo / violet / cyan in the palette — an earlier iteration introduced these for the logo mark, but they didn't match the navy+brass system used everywhere else and have been removed. Keep the palette to navy + brass + red/green going forward; resist adding more accent hues.

## Logo mark
A stylized Greek alpha (Α) shape with the right leg extended into an upward tick and a small dot — reads as both "Alpha" (the letterform) and "ascent/breakout" (the extending line). Rendered as SVG so it stays crisp at favicon size. Drawn in brass on the navy sidebar background.

## Product principle
The public site communicates market intelligence and research methodology.
It does not expose personal portfolio balances, position sizes, cost basis, or account-level returns.
This is also why capital/position-sizing rules (the Excel "资金管理" sheet) are intentionally kept off the public site — only trigger rules and signals are shown, never real allocation amounts.

## Status
1. ✅ Market Regime — implemented (see MARKET_REGIME.md), real breadth data live
2. ✅ Strategy Signal — implemented as "策略引擎" (per-asset 3-tier drawdown triggers)
3. ✅ Data credibility/status — source labels (真实指数/ETF代理) shown per metric
4. ⏳ Research Radar (个股观察池 upgrade) — not yet started
5. ⏳ 历史买点数据库 (historical trigger log) — not yet started
