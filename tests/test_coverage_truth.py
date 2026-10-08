"""#133 B1 / roadmap P1-6: coverage audit truthfulness and upstream completeness ingestion."""
from __future__ import annotations
import importlib.util, io, json, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

cov = load("cov_truth", "data_learning_coverage_audit.py")
sie = load("sie_truth", "source_intelligence_engine.py")

# 1. L6 reuse gate: outcome count alone never keeps learning_active.
with tempfile.TemporaryDirectory() as d:
    sd = Path(d)
    (sd / "event_outcome_memory.py").write_text("OUT='event_outcome_memory.json'", encoding="utf-8")  # producer
    (sd / "system_status_center.py").write_text("x='event_outcome_memory.json'", encoding="utf-8")   # registry only
    (sd / "data_learning_coverage_audit.py").write_text("x='macro_outcome_memory.json'", encoding="utf-8")
    (sd / "planner.py").write_text("x='historical_journal.json'", encoding="utf-8")                  # real consumer
    rows = [
        {"domain": "news_event_evidence", "learning_status": "learning_active", "gaps": []},
        {"domain": "macro_fred_alfred", "learning_status": "learning_active", "gaps": []},
        {"domain": "market_price_history", "learning_status": "learning_active", "gaps": []},
        {"domain": "options_opportunity", "learning_status": "partial_learning", "gaps": []},
        {"domain": "regional_cn_hk_learning", "learning_status": "context_only", "gaps": []},
    ]
    cov.apply_reuse_gate(rows, scripts_dir=sd)
    by = {r["domain"]: r for r in rows}
    assert by["news_event_evidence"]["learning_status"] == "partial_learning"  # producer + registry do not count
    assert any("L6" in g for g in by["news_event_evidence"]["gaps"])
    assert by["macro_fred_alfred"]["learning_status"] == "partial_learning"    # the audit itself does not count
    assert by["market_price_history"]["learning_status"] == "learning_active"
    assert by["market_price_history"]["reused_by"] == ["planner.py"]
    assert by["options_opportunity"]["learning_status"] == "partial_learning"  # never upgraded
    assert by["regional_cn_hk_learning"]["learning_status"] == "context_only"

# 2. Reconciliation is no longer tautological.
ok = cov.reconciliation(10, 10, {"counts": {"source_records": 10}, "text_enrichment": {"text_unavailable_records": 0, "text_enriched_records": 10}}, {})
assert ok["balanced"] is True and ok["errors"] == 0 and ok["errors_known"] is True
lag = cov.reconciliation(10, 12, {"counts": {"source_records": 10}}, {})
assert lag["backlog"] == 2 and lag["balanced"] is False          # canonical not fully read
bad = cov.reconciliation(10, 10, {"counts": {"source_records": 10}, "text_enrichment": {"text_unavailable_records": 3}}, {})
assert bad["errors"] == 3 and bad["balanced"] is False           # title-only reads are errors
yt = cov.reconciliation(10, 10, {"counts": {"source_records": 10}},
                        {"fetch_status": "ok", "youtube": {"seen": 170, "feed_records": 4, "historical_semantic_learned": 4, "unresolved_semantic": 165}})
assert yt["upstream_collector_known"] is True and yt["youtube_seen"] == 170
assert yt["youtube_semantically_learned"] == 8 and yt["youtube_semantic_backlog"] == 165
assert yt["balanced"] is True  # semantic backlog is reported, not hidden, and does not fake an accounting gap

# 3. Upstream completeness contract is actually fetched (INTAKE_STATUS_URL defined) and errors are visible.
assert sie.INTAKE_STATUS_URL.endswith("/wxc-bot/main/state/source_intake_completeness.json")
real = urllib.request.urlopen
class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
try:
    urllib.request.urlopen = lambda req, timeout=None: Resp(json.dumps({"version": 2, "coverage_complete": True, "semantic_learning_complete": False}).encode())
    got = sie.fetch_intake_completeness()
    assert got["version"] == 2 and got["fetch_status"] == "ok" and got["semantic_learning_complete"] is False
    def fail(req, timeout=None): raise OSError("HTTP 404")
    urllib.request.urlopen = fail
    got = sie.fetch_intake_completeness()
    assert got["status"] == "unavailable" and "HTTP 404" in got["fetch_error"] and got["complete"] is False
finally:
    urllib.request.urlopen = real

print("PASS coverage truth: L6 reuse gate / layered reconciliation / upstream completeness fetch")
