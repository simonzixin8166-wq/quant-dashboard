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
- Palette strictly bounded to navy + brass + red/green.

## Logo mark
A stylized Greek alpha (Α) shape SVG rendered in brass on the navy sidebar background, embodying insight and market ascension.

## Product principle
The public site communicates market intelligence and research methodology.
It does not expose personal portfolio balances, position sizes, cost basis, or account-level returns.
This is also why capital/position-sizing rules are intentionally kept off the public site — only trigger rules and signals are shown, never real allocation amounts.

## Status
1. ✅ Market Regime — implemented (see MARKET_REGIME.md), real breadth data live with auto-skip & try-except protection
2. ✅ Strategy Signal — implemented as "策略引擎" (per-asset 3-tier drawdown triggers, including QQQ)
3. ✅ Data credibility/status — source labels (真实指数/ETF代理) shown per metric, plus CN/HK real-time 5s JS ticker
4. ⏳ Research Radar (个股观察池 upgrade) — not yet started
5. ✅ 历史买点数据库 (historical trigger log) — fully implemented as Tab 7 (Archive)
