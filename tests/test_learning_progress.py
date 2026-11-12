"""Learning progress panel: four measures with denominators, unavailable when inputs are missing, append-only
history, never upgrades the learning state, promoted samples never pooled. Synthetic inputs, no network."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import learning_progress as lp

NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)
scores = {"unit_zh": "帖子 × 股票代码", "test_sets": {"t": {"label_zh": "T"}}, "results": [
    {"extractor": "ce-4", "role": "production", "set": "t", "status": "complete", "pred_pairs": 37, "matched": 27, "gold_pairs": 70},
    {"extractor": "g", "role": "challenger", "set": "t", "status": "partial", "answered_posts": 34,
     "pred_pairs": 40, "matched": 40, "gold_pairs": 52},
    {"extractor": "bad", "role": "shadow", "set": "t", "status": "complete", "matched": 3}]}
obs = {"sessions": 25, "observations": 646, "first_session": "2026-10-08", "latest_session": "2026-11-11",
       "continuity": "ok", "gaps": [], "learning_state": "UNPROVEN",
       "horizons": {"20": {"matured_attested": 126, "earliest_maturity": "2026-11-05"},
                    "60": {"matured_attested": 0, "earliest_maturity": "2027-01-05"}}}
card = {"as_of_session": "2026-11-11", "cells": [
    {"group": "genuine_forward", "h": 20, "decision": "A", "eligible": True, "matured": 45, "scored": 45, "hits": 34,
     "abstain": 0, "independent_episodes": 23, "episode_scored": 21, "status": "reportable_minimum_only"},
    {"group": "genuine_forward", "h": 20, "decision": "B", "eligible": False, "matured": 32, "scored": 0, "hits": 0,
     "abstain": 32, "independent_episodes": 15, "episode_scored": 0, "status": "INSUFFICIENT"},
    {"group": "genuine_forward", "h": 60, "decision": "A", "matured": 0, "scored": 0, "hits": 0},
    {"group": "promoted", "h": 20, "decision": "A", "matured": 20, "scored": 20, "hits": 5, "status": "reportable_minimum_only"}]}
attr = {"sessions": ["2026-10-08"], "denominators_including_qqq_qqqm": {"scored": 34}, "misses": 9,
        "misses_by_primary": {"E1": 4}, "attribution_coverage": 1.0, "investment_validity": "INSUFFICIENT"}

d = tempfile.mkdtemp()
hist = Path(d) / "h.jsonl"
r = lp.build(scores, obs, card, attr, [], hist_path=hist, now=NOW)
u, j, e, rel = (r["measures"][k] for k in ("understanding", "judgments", "experience", "reliability"))
assert [x["extractor"] for x in u["rows"]] == ["ce-4", "g"], "rows without full counts are dropped"
assert u["production"]["recall"] == {"k": 27, "n": 70, "value": 0.386, "ci95": [0.28, 0.5]}
assert u["production"]["precision"]["value"] == 0.73
assert u["rows"][1]["recall"]["n"] == 52 and u["rows"][1]["status"] == "partial"
print("PASS 1 understanding: denominators, Wilson intervals, partial runs labelled")

assert j["observations"] == 646 and j["matured_20"] == 77 and j["abstain_20"] == 32 and j["independent_episodes_20"] == 38
print("PASS 2 judgments: abstentions counted, not scored")

assert e["h20"]["scored"] == 45 and e["h20"]["hits"] == 34, "only genuine forward h=20"
assert e["promoted_separate"]["scored"] == 20 and e["categories_total"] == 2 and e["categories_reportable"] == 1
assert e["horizons"]["60"] == {"matured": 0, "earliest_maturity": "2027-01-05"}
print("PASS 3 experience: promoted kept separate, horizons reported")

assert rel["trend_state"] == "INSUFFICIENT" and rel["weeks_recorded"] == 1 and rel["attribution"]["misses"] == 9
assert r["learning_state"] == "UNPROVEN" and r["final"] == "NO"
print("PASS 4 reliability: no trend before 4 weeks; state never upgraded")

# append-only: same session is not rewritten; history grows by session
first = hist.read_text()
lp.build(scores, obs, dict(card, as_of_session="2026-11-11"), attr, lp.read_history(hist), hist_path=hist, now=NOW)
assert hist.read_text() == first
rows = lp.read_history(hist)
for i, s in enumerate(["2026-11-18", "2026-11-25", "2026-12-02"]):
    r = lp.build(scores, obs, dict(card, as_of_session=s), attr, rows, hist_path=hist, now=NOW)
    rows = lp.read_history(hist)
assert len(rows) == 4 and r["measures"]["reliability"]["trend_state"] == "DESCRIPTIVE_ONLY"
print("PASS history append-only, one row per session; 4 weeks -> descriptive only")

# missing inputs -> unavailable, nothing appended
r = lp.build(None, None, None, None, [], hist_path=Path(d) / "none.jsonl", now=NOW)
m = r["measures"]
assert m["understanding"]["status"] == m["judgments"]["status"] == m["experience"]["status"] == "unavailable"
assert not (Path(d) / "none.jsonl").exists() and r["learning_state"] == "UNPROVEN"
print("PASS missing inputs are unavailable, never backfilled")

# the page wiring and the shipped config
cfg = json.loads((ROOT / "config" / "understanding_scores.json").read_text(encoding="utf-8"))
assert all(x["set"] in cfg["test_sets"] for x in cfg["results"])
for p in ("scripts/fetch_and_build.py", "docs/index.html"):
    s = (ROOT / p).read_text(encoding="utf-8")
    assert 'id="learningProgressRoot"' in s and "assets/learning-progress.js" in s and "assets/learning-progress.css" in s, p
js = (ROOT / "docs/assets/learning-progress.js").read_text(encoding="utf-8")
assert "research/learning_progress.json" in js and "不可用" in js and "localStorage" not in js
print("PASS page wiring and config")
