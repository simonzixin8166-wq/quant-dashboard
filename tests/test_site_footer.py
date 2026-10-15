"""C-01 (#133 6138128707 / 6183848571): every public page carries the shared Chinese footer with the three
policy links, the existing feedback email, and the policy page exists with the three anchors. Layout markers,
APP_VERSION and the feedback email are unchanged."""
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
LINKS = ('legal.html#sources', 'legal.html#risk', 'legal.html#correction')
CORE = "部分资料来自第三方公开来源，著作权和观点归相应权利人"
NOT_ENDORSED = "不代表原作者认可、授权、合作或赞助"
gen = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")
for name in ("index.html", "brightline-2026.html"):
    html = (ROOT / "docs" / name).read_text(encoding="utf-8")
    assert CORE in html and NOT_ENDORSED in html and "不构成个性化建议" in html, name
    assert all(f'href="{l}"' in html for l in LINKS), name
    assert 'href="mailto:xxj8166@gmail.com"' in html, name
assert CORE in gen and all(f'href="{l}"' in gen for l in LINKS)       # the Daily generator keeps the same footer
idx = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
assert 'footer footer-with-analytics' in idx and 'id="siteAnalyticsRoot"' in idx   # analytics slot preserved
legal = (ROOT / "docs" / "legal.html").read_text(encoding="utf-8")
for anchor in ("sources", "risk", "correction", "changes"):
    assert f'id="{anchor}"' in legal, anchor
assert "xxj8166@gmail.com" in legal and "不构成任何投资建议" in legal and "不表示本声明自动取得任何转载或改编许可" in legal
assert not re.search(r"授权转载|已获授权", legal)                     # never claims a licence
from importlib import util
spec = util.spec_from_file_location("app_version", ROOT / "scripts" / "app_version.py"); av = util.module_from_spec(spec); spec.loader.exec_module(av)
assert av.APP_VERSION == "6.9.0"
print("test_site_footer OK")
