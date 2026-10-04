import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

ui=(ROOT/"docs"/"assets"/"knowledge.js").read_text(encoding="utf-8")

# Dynamic Source Reading provenance cards must exist.
assert "function sourceReadingRecordHtml" in ui
assert "来源拆解预览" in ui
assert "优先展示含可验证规则的来源" in ui
assert "每条来源最多展示6个命题" in ui

# All six semantic kinds remain visible in the UI.
for label in ("Fact","Author View","Trigger","Invalidation","Testable Rule","Non-testable View"):
    assert label in ui

# Provenance and original-source review are preserved.
assert "r.author" in ui
assert "r.source" in ui
assert "r.published_at" in ui
assert "link(r.url" in ui

# Ranking is presentation-only and cannot mutate production behavior.
assert "testable_rule_count" in ui
for forbidden in ("automatic_order","production_threshold_change","position_size_change","forward_ledger_write"):
    assert forbidden not in ui.lower()

version=(ROOT/"scripts"/"app_version.py").read_text(encoding="utf-8")
assert '"source_reading_ui": "6.14.7"' in version
assert 'APP_VERSION = "6.9.0"' in version

print("PASS V6.14.7 dynamic Source Reading provenance UI / six kinds / research-only presentation")
