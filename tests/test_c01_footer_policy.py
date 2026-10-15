"""C-01: shared Chinese footer links + policy page; feedback email and APP_VERSION unchanged; no licensing claim."""
import re
from pathlib import Path
R = Path(__file__).resolve().parents[1]
EMAIL = "xxj8166@gmail.com"
LINKS = ['href="policy.html#sources"', 'href="policy.html#risk"', 'href="policy.html#correction"']
policy = (R / "docs/policy.html").read_text(encoding="utf-8")
for anchor in ("sources", "risk", "correction"):
    assert f'id="{anchor}"' in policy, anchor
assert EMAIL in policy and 'lang="zh-CN"' in policy and 'name="viewport"' in policy
assert "不构成任何投资建议" in policy and "不保存、不转载第三方全文" in policy
assert not re.search(r"已获(得)?(授权|许可)转载", policy)
for f in ("docs/index.html", "scripts/fetch_and_build.py", "docs/brightline-2026.html"):
    s = (R / f).read_text(encoding="utf-8")
    for l in LINKS:
        assert l in s, (f, l)
    assert f"mailto:{EMAIL}" in s, f
gen = (R / "scripts/fetch_and_build.py").read_text(encoding="utf-8")
assert 'footer footer-with-analytics' in gen and "意见交流邮箱：" in gen
assert re.search(r'APP_VERSION\s*=\s*"6\.9\.0"', (R / "scripts/app_version.py").read_text(encoding="utf-8"))
print("PASS C-01 Chinese footer + policy page")
