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

# Near-duplicate: same author, forum repost of a blog post with a prefixed title and a few
# changed characters, same day -> one independent claim. Provenance of both is kept.
body="LITE 是光通信龙头，基本面持续改善。我计划在 LITE 跌到 860 附近卖出 Sell Put，行权价 800，跌破 760 就止损认错。"*3
near=[
 {"id":"blog1","author":"Z","source_kind":"blog","published_at":"2026-09-30","title":"LITE 适合 Sell Put 的理由",
  "excerpt":body,"captured_at":"2026-10-01T01:00:00Z"},
 {"id":"forum1","author":"Z","source_kind":"forum","published_at":"2026-09-30 14:09:50","title":"分享 LITE 适合 Sell Put 的理由",
  "excerpt":body.replace("860","865"),"captured_at":"2026-10-01T02:00:00Z"},
 # Same author, same title, but a different week and a different hypothesis: must NOT merge.
 {"id":"forum2","author":"Z","source_kind":"forum","published_at":"2026-10-20","title":"LITE 适合 Sell Put 的理由",
  "excerpt":"今天 LITE 跌破 760，原来的 Sell Put 计划失效，我认错止损，接下来只观察不加仓。"*3,"captured_at":"2026-10-20T02:00:00Z"},
 # Same text but a different author: not a same-author repost (exact pass handles true copies).
 {"id":"other","author":"W","source_kind":"forum","published_at":"2026-09-30","title":"转贴",
  "excerpt":body.replace("860","870"),"captured_at":"2026-10-01T03:00:00Z"},
 # Same author, same channel, identical text but different titles: not a cross-channel copy.
 {"id":"v1","author":"V","source_kind":"blog","published_at":"2026-09-30","title":"第一篇",
  "excerpt":body,"captured_at":"2026-10-01T04:00:00Z"},
 {"id":"v2","author":"V","source_kind":"blog","published_at":"2026-09-30","title":"第二篇",
  "excerpt":body,"captured_at":"2026-10-01T05:00:00Z"},
]
n=build(near)
m=n["mapping"]
assert n["counts"]["near_groups"]==1, n["counts"]
assert m["blog1"]["duplicate_of"] is None and m["blog1"]["match_basis"]=="near_text_same_author"
assert m["forum1"]["duplicate_of"]=="blog1" and m["forum1"]["evidence_weight_class"]=="duplicate_evidence"
assert "forum2" not in m and "other" not in m
assert "v1" not in m and "v2" not in m
# Lightly edited text below the 0.90 similarity bar is not merged.
from source_duplicate_audit import near_duplicate
edited={"author":"Z","source_kind":"forum","published_at":"2026-09-30","excerpt":body.replace("860","865")}
other={"author":"Z","source_kind":"blog","published_at":"2026-09-30","excerpt":body.replace("800","805")}
assert near_duplicate(edited,other) is False
print("PASS same-author cross-channel near-duplicate evidence / no topic-only merge")
