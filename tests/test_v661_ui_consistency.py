from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from app_version import APP_VERSION,ASSET_VERSION
gen=(ROOT/"scripts"/"fetch_and_build.py").read_text(encoding="utf-8")
idx=(ROOT/"docs"/"index.html").read_text(encoding="utf-8")
mobile=(ROOT/"docs"/"assets"/"mobile-shell.js").read_text(encoding="utf-8")
agent=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")

assert APP_VERSION == "6.9.0"
assert ASSET_VERSION == APP_VERSION
assert "from app_version import APP_VERSION, OPTIONS_VERSION, ASSET_VERSION" in gen
assert 'application-version" content="6.9.0"' in idx
assert 'data-app-version="6.9.0"' in idx
assert '?v=5.3.0' not in idx
assert 'MyAlpha View V6.9.0' in idx
assert 'Options Engine V4.1.0' in idx

for label in ["今日驾驶舱","AI智能中心","市场中心","个股研究","期权中心","策略中心","研究中心","复盘与学习","工具","系统"]:
    assert label in gen
    assert label in idx

for old in [">Agent Center<",">Markets<",">Stocks<",">Options<",">Strategy<",">Research<",">Journal / Learning<",">Tools<",">System<"]:
    assert old not in gen
    assert old not in idx

assert "label:'智能'" in mobile
assert "label:'个股'" in mobile
assert "label:'期权'" in mobile
assert "打开 AI智能中心" in agent
print("PASS V6.9.0 UI/version consistency")
