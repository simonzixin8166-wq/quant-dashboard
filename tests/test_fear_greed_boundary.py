"""CNN Fear & Greed: link-out only until a compliant data source is approved (#133 item 10)."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")
assert 'href="https://www.cnn.com/markets/fear-and-greed"' in src and "本站不抓取、不转载数值" in src
# no automated access to CNN's undocumented data endpoint anywhere in scripts or site code
for p in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "docs" / "assets").glob("*.js")):
    t = p.read_text(encoding="utf-8", errors="ignore")
    assert "dataviz.cnn.io" not in t and "fearandgreed/graphdata" not in t, p
print("PASS fear & greed boundary")
