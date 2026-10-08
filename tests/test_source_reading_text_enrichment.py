"""#133 regression: Source Reading must parse source text, not only titles.

665bba8 made Source Reading consume the canonical Source Store snapshot, which
does not persist `excerpt` or primary-subject attribution. This test proves the
canonical store still decides the record set, text is re-attached from the
normalized stream, unmatched records are marked, and a missing stream fails closed.
No network: the normalized stream is stubbed with synthetic text.
"""
from __future__ import annotations
import importlib.util, json, os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("srm_enrich", ROOT / "scripts" / "source_reading_memory.py")
srm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srm)
import source_intelligence_engine as sie  # noqa: E402

RAW = {
    "id": "synthetic_lite_0001", "source": "wenxuecity", "source_kind": "forum", "author": "test_author",
    "published_at": "2026-09-30 14:09:50", "url": "https://example.invalid/cfzh/1.html",
    "title": "LITE 适合 Sell Put 的理由(结合图)",
    "excerpt": ("LITE 是光通信龙头，基本面持续改善。我计划在 LITE 跌到 860 附近卖出 Sell Put，"
                "行权价 800，跌破 760 就止损认错。QQQ 只是大盘参照。"
                "如果 MA50 被有效跌破，这个计划就失效。"),
    "symbols": ["QQQ"], "captured_at": "2026-10-01T01:27:35Z",
    "intake_class_hint": "backfill", "capture_mode": "recovered_git_history",
}
OFFLINE = {"id": "synthetic_offline_0002", "source": "wenxuecity", "source_kind": "blog",
           "author": "test_author", "published_at": "2026-09-25", "url": "https://example.invalid/b/2.html",
           "title": "一篇已下线的旧文章", "symbols": [], "operations": []}

normalized = sie.normalize_records([RAW])
assert normalized and normalized[0].get("excerpt"), "fixture must produce normalized text"
assert normalized[0].get("primary_symbols") == ["LITE"], normalized[0].get("primary_symbols")

# Store snapshot exactly as v615_persistent_source_store persists it: no excerpt/attribution.
SNAP_KEYS = ("id", "source", "source_kind", "author", "published_at", "title", "url", "symbols", "topics",
             "operations", "method_signals", "content_chars", "captured_at", "intake_class_hint", "capture_mode")
store_lite = {k: normalized[0].get(k) for k in SNAP_KEYS}
store = {"records": [
    {"source_key": RAW["id"], "admission_class": "backfill", "record": store_lite},
    {"source_key": OFFLINE["id"], "admission_class": "initial_migration", "source_still_online": False, "record": OFFLINE},
]}

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    srm.STORE = tmp / "source_store.json"; srm.STORE.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    srm.DUPMAP = tmp / "dup.json"; srm.DUPMAP.write_text(json.dumps({"mapping": {}}), encoding="utf-8")
    srm.SRC = tmp / "si.json"; srm.SRC.write_text(json.dumps({"records": []}), encoding="utf-8")
    srm.OUT = tmp / "reading.json"

    # Title-only baseline = the regressed behaviour.
    title_only = srm.build({"records": [dict(store_lite)]})
    base_rec = title_only["records"][0]

    srm.load_normalized_stream = lambda: normalized
    srm.main()
    out = json.loads(srm.OUT.read_text(encoding="utf-8"))
    recs = {r["source_id"]: r for r in out["records"]}

    # Canonical store still defines the record set (both rows, including the offline one).
    assert set(recs) == {RAW["id"], OFFLINE["id"]}, set(recs)
    te = out["text_enrichment"]
    assert te["text_enriched_records"] == 1 and te["text_unavailable_records"] == 0, te
    assert te["source_offline_records"] == 1 and te["online_text_coverage"] == 1.0, te
    assert recs[OFFLINE["id"]]["source_id"] == OFFLINE["id"]

    lite = recs[RAW["id"]]
    assert lite["primary_symbols"] == ["LITE"], lite["primary_symbols"]
    assert len(lite["propositions"]) > len(base_rec["propositions"]), (len(lite["propositions"]), len(base_rec["propositions"]))
    assert base_rec["primary_symbols"] != ["LITE"]

    # Provenance stays canonical: enrichment never rewrites admission fields.
    assert store_lite["intake_class_hint"] == "backfill"

    # Fail closed: stream unavailable -> raise and keep the previous artifact untouched.
    before = srm.OUT.read_text(encoding="utf-8")
    def boom():
        raise RuntimeError("network down")
    srm.load_normalized_stream = boom
    try:
        srm.main()
        raise AssertionError("Source Reading must fail closed without source text")
    except RuntimeError as exc:
        assert "fails closed" in str(exc)
    assert srm.OUT.read_text(encoding="utf-8") == before

# Failure injection: stream reachable but canonical ids do not match (e.g. id scheme drift).
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    online_store = {"records": [{"source_key": RAW["id"], "admission_class": "backfill", "record": store_lite}]}
    srm.STORE = tmp / "s.json"; srm.STORE.write_text(json.dumps(online_store, ensure_ascii=False), encoding="utf-8")
    srm.DUPMAP = tmp / "dup.json"; srm.DUPMAP.write_text(json.dumps({"mapping": {}}), encoding="utf-8")
    srm.SRC = tmp / "si.json"; srm.SRC.write_text(json.dumps({"records": []}), encoding="utf-8")
    srm.OUT = tmp / "reading.json"; srm.OUT.write_text('{"sentinel": true}', encoding="utf-8")
    drifted = [dict(normalized[0], id="other_id", url="https://example.invalid/elsewhere")]
    srm.load_normalized_stream = lambda: drifted
    try:
        srm.main()
        raise AssertionError("low text coverage must fail closed")
    except RuntimeError as exc:
        assert "matched only 0/1" in str(exc), exc
    assert json.loads(srm.OUT.read_text(encoding="utf-8")) == {"sentinel": True}

    # Semantic regression guard: a previous enriched artifact with far more propositions blocks overwrite.
    srm.load_normalized_stream = lambda: normalized
    srm.OUT.write_text(json.dumps({"text_enrichment": {"text_enriched_records": 1},
                                   "counts": {"source_records": 1, "propositions": 999, "candidate_rules": 0}}), encoding="utf-8")
    try:
        srm.main()
        raise AssertionError("semantic regression must fail closed")
    except RuntimeError as exc:
        assert "semantic regression" in str(exc) and "propositions 999->" in str(exc), exc
    assert json.loads(srm.OUT.read_text(encoding="utf-8"))["counts"]["propositions"] == 999

    # Explicit, recorded override for an intentional parser change.
    os.environ[srm.ALLOW_DROP_ENV] = "1"
    try:
        srm.main()
    finally:
        os.environ.pop(srm.ALLOW_DROP_ENV, None)
    overridden = json.loads(srm.OUT.read_text(encoding="utf-8"))
    assert overridden.get("semantic_drop_override") is True

    # Pre-enrichment (regressed title-only) artifacts never block the recovery itself.
    assert srm.semantic_regression_guard({"counts": {"source_records": 1, "propositions": 999}}, overridden) is None
    # A shrinking source set is not treated as a parser regression.
    assert srm.semantic_regression_guard(
        {"text_enrichment": {}, "counts": {"source_records": 5, "propositions": 999}},
        {"counts": {"source_records": 4, "propositions": 1}}) is None

# Unit: identity/provenance fields are never taken from the normalized stream.
rows, stats = srm.enrich_with_source_text(
    [{"id": "x", "url": "u", "intake_class_hint": "backfill", "captured_at": "A"}],
    [{"id": "x", "url": "u", "excerpt": "text", "intake_class_hint": "live_candidate", "captured_at": "B"}])
assert rows[0]["excerpt"] == "text" and rows[0]["intake_class_hint"] == "backfill" and rows[0]["captured_at"] == "A"
assert stats == {"text_enriched_records": 1, "text_unavailable_records": 0, "source_offline_records": 0, "online_text_coverage": 1.0}

print("PASS #133 Source Reading text enrichment / canonical set / fail-closed")
