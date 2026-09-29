from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
g=(ROOT/'scripts/fetch_and_build.py').read_text(encoding='utf-8')
p=(ROOT/'docs/index.html').read_text(encoding='utf-8')
js=(ROOT/'docs/assets/investment-assistant.js').read_text(encoding='utf-8')
stock=(ROOT/'docs/assets/stock-watchlist.js').read_text(encoding='utf-8')
wxc=(ROOT/'docs/assets/wenxuecity.js').read_text(encoding='utf-8')
methods=(ROOT/'docs/assets/research-methods.js').read_text(encoding='utf-8')
css=(ROOT/'docs/assets/design-v4.8.css').read_text(encoding='utf-8')

assert 'APP_VERSION = "5.0.0"' in g and 'ASSET_VERSION = "5.0.0"' in g
assert 'id="marketOptionAlert"' in g and 'id="marketOptionAlert"' in p
assert 'marketOptionAlert' in js and '30–45 DTE' in methods and 'Delta 0.16–0.20' in methods
assert 'LEAPS Call 研究候选' in methods and '12–24个月以上' in methods
assert "globalThis.MAVInvestmentAssistant?.updateFromMarket?.(body)" in (ROOT/'docs/assets/market-live.js').read_text(encoding='utf-8')
assert 'trend-zone-mini' in stock and 'trend-stage-mini' in stock
assert '↗ 回踩后重新转强' in stock and '↘ 分数仍高但正在转弱' in stock
assert '先看位置，再看方向' in g and '先看位置，再看方向' in p
assert '策略经验库 · 先作为研究候选' in wxc
assert '查看后台采集技术状态' in wxc and '当前有来源暂不可用' in wxc
assert 'footer-main #siteAnalyticsRoot.site-analytics' in css
assert '期权决策与推演' in g and '期权决策与推演' in p
print('test_v500_investment_assistant.py: all assertions passed')
