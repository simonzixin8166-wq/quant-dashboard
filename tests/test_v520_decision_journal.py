from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
g=(ROOT/'scripts/fetch_and_build.py').read_text()
idx=(ROOT/'docs/index.html').read_text()
ja=(ROOT/'docs/assets/decision-journal.js').read_text()
ia=(ROOT/'docs/assets/investment-assistant.js').read_text()
sw=(ROOT/'docs/assets/stock-watchlist.js').read_text()
edge=(ROOT/'supabase/functions/stock-market/index.ts').read_text()
wf=(ROOT/'.github/workflows/daily.yml').read_text()

sys.path.insert(0,str(ROOT/'scripts'))
from app_version import APP_VERSION,ASSET_VERSION
app_version=APP_VERSION
asset_version=ASSET_VERSION
assert "from app_version import APP_VERSION, OPTIONS_VERSION, ASSET_VERSION" in g
assert 'tab-journal' in g and 'decisionJournalRoot' in g
assert 'decision-journal.js' in g and 'decision-journal.css' in g
assert 'Decision Journal' in idx and f'data-app-version="{app_version}"' in idx
assert f'decision-journal.js?v={asset_version}' in idx
assert "mavDecisionJournalV52" in ja
assert '20 / 60 / 120' in ja and 'refreshOutcomes' in ja
assert 'latestCompleteMarketDate' in ja
assert "marketDateSource:'complete_daily_close'" in ja
assert "priceSource:'complete_daily_close'" in ja
assert "filter(x=>!isWeekendDate" in ja
assert '等待第${h}个交易日收盘' in ja
assert '<th>交易日</th>' in ja and '<th>收盘入档价</th>' in ja
assert 'recordAssistantEvent' in ia and 'MAVDecisionJournal' in ia
assert 'assistant-inline-actions' in ia and 'StockWatchlist.focus' in ia and 'OptionV2.openForSymbol' in ia
assert 'pulseText' in sw and "r===0?'0'" in sw
assert "type Scope = 'quote' | 'daily' | 'history' | 'all'" in edge and 'historyRows' in edge
assert 'backtest_assistant_rules.py' in wf and 'test_v520_decision_journal.py' in wf
print('V5.2 decision journal contract: PASS')
