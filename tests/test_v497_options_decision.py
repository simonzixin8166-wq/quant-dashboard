from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from app_version import APP_VERSION,OPTIONS_VERSION
def test_v497():
    src=(ROOT/'scripts/fetch_and_build.py').read_text()
    js=(ROOT/'docs/assets/options-v2.js').read_text()
    css=(ROOT/'docs/assets/options-v2.css').read_text()
    a=(ROOT/'docs/assets/site-analytics.js').read_text()
    assert APP_VERSION == "6.8.2" and OPTIONS_VERSION == "4.1.0"
    assert "from app_version import APP_VERSION, OPTIONS_VERSION, ASSET_VERSION" in src
    assert 'optionDecisionSummary' in src and 'decisionCatalystDate' in src
    assert 'renderDecisionAssistant' in js and '不是胜率' in js and '没有上限' in js
    assert '.option-decision-assistant' in css
    assert 'site-analytics-card' not in a and '匿名访问统计' in a
