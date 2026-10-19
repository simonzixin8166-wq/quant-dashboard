"""全站紧凑排版 (#133 6258076746): the compact token sheet is loaded last and stays spacing/type/colour only.
Guards the boundary from #133 6258163948: no fixed-height caps, no hidden overflow, no display/visibility changes
(auth-gated and private elements keep whatever visibility the existing sheets give them)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / "docs" / "assets" / "compact-layout.css").read_text(encoding="utf-8")
build = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")

# loaded last, after every other stylesheet in the page head
link = '<link rel="stylesheet" href="assets/compact-layout.css?v={ASSET_VERSION}"></head>'
assert link in build, "compact-layout.css must be the last stylesheet before </head>"

body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
decls = [d.strip().split(":", 1)[0].strip() for block in re.findall(r"\{([^{}]*)\}", body) for d in block.split(";") if ":" in d]
forbidden = {"display", "visibility", "overflow", "overflow-x", "overflow-y", "max-height", "min-height", "clip", "clip-path",
             "opacity", "position", "content", "text-overflow", "-webkit-line-clamp"}
assert not (set(decls) & forbidden), sorted(set(decls) & forbidden)
# the only height set is the desktop top bar, via its token
heights = [d for d in decls if d == "height"]
assert len(heights) == 1 and ".topbar{height:var(--mc-topbar-h)!important}" in body.replace(" ", "")
# status/risk colours are untouched: colour rules only target titles, the research banner and the theme button
for sel in re.findall(r"([^{}]+)\{[^{}]*(?:color|background)[^{}]*\}", body):
    sel = sel.strip()
    if sel.startswith(":root"):
        continue
    assert re.search(r"\.(hero|compact-hero|overview-hero|single-action-banner|theme-toggle)\b", sel), sel
assert "@media (min-width:821px)" in css and "@media (max-width:820px)" in css  # mobile-shell.css owns <=820px
print("PASS compact layout: loaded last; spacing/type/colour only; no visibility, overflow or height caps")
