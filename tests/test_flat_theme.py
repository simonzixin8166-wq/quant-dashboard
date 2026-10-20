"""UI-02 扁平样式: flat-theme.css is pulled in by compact-layout.css (so old and new index.html both get it) and stays
cosmetic: surfaces, borders, shadows, radius, tab buttons. It must never hide, move, clip or cap anything, and it must
not recolour status / risk / price elements."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
compact = (ROOT / "docs" / "assets" / "compact-layout.css").read_text(encoding="utf-8")
flat = (ROOT / "docs" / "assets" / "flat-theme.css").read_text(encoding="utf-8")

# transition-safe loading: imported from the sheet every live index.html already links; @import must precede all rules
body_compact = re.sub(r"/\*.*?\*/", "", compact, flags=re.S).strip()
assert body_compact.startswith('@import url("flat-theme.css'), "flat-theme.css must be the first statement of compact-layout.css"

body = re.sub(r"/\*.*?\*/", "", flat, flags=re.S)
assert "@import" not in body
decls = [d.strip().split(":", 1)[0].strip() for block in re.findall(r"\{([^{}]*)\}", body) for d in block.split(";") if ":" in d]
allowed = {"background", "background-image", "background-color", "border", "border-color", "border-bottom", "border-bottom-color",
           "border-radius", "box-shadow", "color", "font-weight", "gap", "padding", "padding-left", "padding-right",
           "--card", "--accent-soft"}
assert set(decls) <= allowed, sorted(set(decls) - allowed)

# every selector targets a page surface, a title frame or a tab strip; never a badge/pill/status/price class
surface = re.compile(r"(\.hero|\.overview-hero|\.finance-hero|\.research-shell|\.invest-action-strip|\.auto-research-row|"
                     r"\.macro-event-row|\.iren-brief|\.trend-method-note|\.panel|\.metric-card|\.mkt-card|\.card|\.finance-card|"
                     r"\.finance-mode-panel|\.agent-card|\.journal-panel|\.wxc-box|\.public-access-gate|\.wxc-hero|"
                     r"\.wxc-operation-inline|\.wxc-progress|\.wxc-tabs|\.wxc-primary-tabs|\.kh-tabs|\.finance-view-tabs|"
                     r"\.finance-mode-tabs|#wxcRoot|#knowledgeRoot|^html(:not\(\[data-theme=\"dark\"\]\))?( body)?$)")
banned = re.compile(r"badge|pill|status|risk|price|chg|change|up\b|down\b|signal|alert|tag\b|chip", re.I)
selectors = [s.strip() for group in re.findall(r"([^{}]+)\{", body) for s in group.split(",")]
selectors = [s for s in selectors if s and not s.startswith("@media")]
assert selectors, "no selectors parsed"
for sel in selectors:
    assert surface.search(sel), sel
    assert not banned.search(sel), sel

# light rules are scoped away from dark mode so the existing dark surfaces keep winning
assert 'html:not([data-theme="dark"]),html:not([data-theme="dark"]) body{background:#f4f3ef' in body.replace("\n", "")
print(f"PASS flat theme: imported first by compact-layout.css; {len(selectors)} cosmetic selectors; no layout/visibility or status colours")
