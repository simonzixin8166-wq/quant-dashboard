from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from source_duplicate_audit import build

rows=[
 {"id":"a","author":"X","source_kind":"blog","title":"A sufficiently long repeated thesis title","excerpt":"same evidence text "*8,"captured_at":"2026-10-01T00:00:00Z"},
 {"id":"b","author":"X","source_kind":"forum","title":"A sufficiently long repeated thesis title","excerpt":"same evidence text "*8,"captured_at":"2026-10-02T00:00:00Z"},
 {"id":"c","author":"Y","source_kind":"forum","title":"A sufficiently long repeated thesis title","excerpt":"same evidence text "*8,"captured_at":"2026-10-02T00:00:00Z"},
]
out=build(rows)
assert out["counts"]["duplicate_groups"]==1
assert out["counts"]["duplicate_records"]==2
assert out["mapping"]["a"]["duplicate_of"] is None
assert out["mapping"]["b"]["duplicate_of"]=="a"
assert out["mapping"]["c"]["duplicate_of"]=="a"
print("PASS cross-channel/author-independent exact duplicate evidence audit")
