from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
g=(ROOT/'scripts/fetch_and_build.py').read_text(encoding='utf-8')
p=(ROOT/'docs/index.html').read_text(encoding='utf-8')
a=(ROOT/'docs/assets/investment-assistant.js').read_text(encoding='utf-8')
o=(ROOT/'docs/assets/options-v2.js').read_text(encoding='utf-8')
r=(ROOT/'docs/assets/research-methods.js').read_text(encoding='utf-8')
s=(ROOT/'docs/assets/stock-watchlist.js').read_text(encoding='utf-8')
sys.path.insert(0,str(ROOT/'scripts'))
from app_version import APP_VERSION,ASSET_VERSION
app_version=APP_VERSION
asset_version=ASSET_VERSION
assert "from app_version import APP_VERSION, OPTIONS_VERSION, ASSET_VERSION" in g
assert f'application-version" content="{app_version}"' in p
assert f'?v={asset_version}' in p
assert 'MYALPHA_RULE_REGISTRY' in r
for token in ['market-watch','market-fear','market-panic','sell-put-fear','buy-call-repair','leaps-long-term','thesis-required','data-freshness']:
    assert token in r
for token in ["ixic<=-.015","ixic<=-.025","ixic<=-.04","spx<=-.0125","spx<=-.02","spx<=-.035","vix>=25","vix>=28","vix>=35"]:
    assert token in a
assert 'mavDecisionJournalV51' in a and 'recordEvent' in a
assert 'notifyTransition' in a and 'lastAlertKey' in a
assert 'scheduleOptionScan' in a and 'autoScreenOpportunity' in o
assert "Math.abs(Number(x.delta))>=.16" in o and "Math.abs(Number(x.delta))<=.20" in o
assert 'bestExpiry(exps,30,45,37)' in o
assert 'bestExpiry(exps,365,760,540)' in o
assert '不会自动下单' in a and '不得自动下单' in r
assert 'MAVInvestmentAssistant?.rescan?.()' in s
print('test_v510_autonomous_assistant.py: all assertions passed')
