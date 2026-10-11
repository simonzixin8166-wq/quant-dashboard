"""#133 6109957428 P0-2: third-party scripts are pinned to exact versions with SRI, the fallback uses the same
version and hash, and the guard loads before any inline code touches Chart / supabase."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
GEN = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")
FALLBACK = (ROOT / "docs" / "assets" / "vendor-fallback.js").read_text(encoding="utf-8")

for name, text in (("page", PAGE), ("generator", GEN)):
    tags = re.findall(r'<script[^>]+src="(https://[^"]+)"[^>]*>', text)
    assert tags, f"{name}: no external scripts found"
    for t in re.findall(r'<script[^>]+src="https://[^"]+"[^>]*>', text):
        src = re.search(r'src="([^"]+)"', t).group(1)
        assert re.search(r'@\d+\.\d+\.\d+/', src), f"{name}: floating version in {src}"
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/=]{64}"', t), f"{name}: missing SRI on {src}"
        assert 'crossorigin="anonymous"' in t, f"{name}: missing crossorigin on {src}"
        path = src.split("/npm/", 1)[1]
        integrity = re.search(r'integrity="([^"]+)"', t).group(1)
        assert f"'{path}'" in FALLBACK and f"'{integrity}'" in FALLBACK, f"{name}: fallback not aligned for {path}"
    assert "chart.js@4\"" not in text and "supabase-js@2\"" not in text, f"{name}: floating major tag left"
    i_guard, i_fb = text.find("assets/vendor-guard.js"), text.find("assets/vendor-fallback.js")
    assert 0 < i_fb < i_guard, f"{name}: fallback must precede guard"
    assert i_guard < text.find("supabase.createClient("), f"{name}: guard must load before createClient"
    assert i_guard < text.find("new Chart("), f"{name}: guard must load before first chart"
assert '<meta name="application-version" content="6.9.0">' in PAGE, "public APP_VERSION must stay 6.9.0"
print("test_vendor_pinning OK")
