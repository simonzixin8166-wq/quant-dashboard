from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/".github/workflows/source-intelligence-validation.yml").read_text(encoding="utf-8")
daily=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")

# Both production writers that can refresh Source Intelligence must generate
# the dependent Source Reading artifact before committing public outputs.
for text,name in ((source,"source-intelligence"),(daily,"daily")):
    assert "python scripts/source_reading_memory.py" in text, name
    assert "scripts/source_reading_memory.py" in text, name

assert "docs/research/source_reading_memory.json" in source
assert source.index("Build source intelligence") < source.index("Build V6.14 Source Reading Memory")
assert source.index("Build V6.14 Source Reading Memory") < source.index("Build source outcome validation")
assert "python tests/test_v614_source_reading_memory.py" in source
assert "node --check docs/assets/knowledge.js" in source

# Shared writer serialization remains required.
assert "group: myalpha-production-writer" in source
assert "ref: main" in source
assert "git pull --rebase origin main" in source
assert "git push origin HEAD:main" in source

print("PASS V6.14.1 source-writer artifact parity / no transient Source Reading 404")
