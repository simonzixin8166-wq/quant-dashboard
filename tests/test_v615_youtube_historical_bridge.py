import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("si",ROOT/"scripts"/"source_intelligence_engine.py")
si=importlib.util.module_from_spec(spec); spec.loader.exec_module(si)

live=[{"id":"live1","source":"wenxuecity","source_kind":"forum","author":"A","published_at":"2026-10-05","title":"QQQ update","url":"https://example/live","excerpt":"QQQ trend"}]
hist={"version":1,"generated_at":"2026-10-05T00:00:00Z","records":[{
    "archive_id":"yt_hist_guard","author":"老李玩钱","video_id":"x","title":"historical",
    "quality":"Q2","historical_learning_eligible":True,
    "forward_evidence_eligible":True,"promotion_eligible":True,"event_score_eligible":True,
    "operations":[{"actions":["buy"],"attribution":"author_plan"}],
}],"counts":{"records":1,"q1_q2_learning_eligible":1}}

out=si.build(live,youtube_historical_learning=hist)
assert "historical_learning" in out
assert "youtube_historical_learning" not in out
assert out["counts"]["records"]==1
assert all(r.get("archive_id")!="yt_hist_guard" for r in out["records"])
h=out["historical_learning"]
assert h["non_gating"] is True and h["result_blind"] is True
r=h["records"][0]
for k in ["forward_evidence_eligible","promotion_eligible","event_score_eligible","source_store_eligible","rule_registry_eligible"]:
    assert r[k] is False, (k,r)

# Downstream production-evidence consumers must not gain a historical-learning intake.
for rel in [
    "scripts/v615_persistent_source_store.py",
    "scripts/v615_rule_registry.py",
    "scripts/v615_event_score.py",
    "scripts/v615_promotion_gate.py",
]:
    text=(ROOT/rel).read_text(encoding="utf-8")
    assert "historical_learning" not in text, rel

print("PASS V6.15 historical-learning bridge hard isolation")
