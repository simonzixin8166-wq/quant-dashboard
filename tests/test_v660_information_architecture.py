from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
gen=(ROOT/"scripts"/"fetch_and_build.py").read_text(encoding="utf-8")
idx=(ROOT/"docs"/"index.html").read_text(encoding="utf-8")
mobile=(ROOT/"docs"/"assets"/"mobile-shell.js").read_text(encoding="utf-8")

def sidebar(html):
    m=re.search(r'<aside class="sidebar">(.*?)</aside>',html,re.S)
    assert m
    return m.group(1)

for html in (gen,idx):
    side=sidebar(html)
    # 8 core + 2 auxiliary
    ids=re.findall(r"switchTab\('([^']+)'",side)
    assert len(ids)==10, ids
    expected=[
      "tab-overview","tab-agent-center","tab-index","tab-stocks","tab-options",
      "tab-engine","tab-wenxuecity","tab-journal","tab-finance-tools","tab-system-health"
    ]
    assert ids==expected, ids
    for hidden in ["tab-cn-hk","tab-trend-pulse","tab-sandbox","tab-archive","tab-knowledge"]:
        assert f'id="{hidden}"' in html
        assert hidden not in ids
    assert 'id="tab-agent-center"' in html
    assert 'id="agentCenterRoot"' in html
    assert "Trend Pulse 详情" in html
    assert "Sandbox / 推演" in html
    assert "知识与方法库" in html

assert "tab-agent-center" in mobile
assert "label:'智能'" in mobile
print("PASS V6.6 consolidated information architecture")

# V6.6.1 Chinese mobile navigation contract
