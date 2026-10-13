"""B1: experience is Shadow evidence only — matured, no look-ahead, no unverified author data, never changes stance."""
import copy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import experience_inputs as xp  # noqa: E402

mem = {"meta": {"learning": {"sha256": "L" * 64, "as_of": "2026-10-09"}, "evidence": {"sha256": "E" * 64}},
       "learning": {"situation_memory": [{"symbol": "MSFT", "timestamp": "2026-10-09", "stage": "二次启动", "similarity": {"method": "technical-v1", "matches": [
           {"symbol": "NVDA", "date": "2026-05-08", "stage": "二次启动", "similarity": 99.9, "return_60": 0.02, "mae_60": -0.11},
           {"symbol": "AMD", "date": "2025-01-02", "stage": "二次启动", "similarity": 95.0, "return_60": -0.08, "mae_60": -0.2},
           {"symbol": "VIX", "date": "2026-03-24", "stage": "二次启动", "similarity": 99.9, "return_60": -0.3},
           {"symbol": "TSLA", "date": "2026-09-01", "stage": "二次启动", "similarity": 90.0, "return_60": None},
           {"symbol": "GOOG", "date": "2026-08-20", "stage": "二次启动", "similarity": 88.0, "return_60": 0.05}]}}]},
       "evidence": {"failure_attribution": {"mature_samples_scanned": 510, "review_samples": 197, "tag_counts": {"trend_false_positive": 9},
           "recent": [{"symbol": "MSFT", "date": "2026-08-03", "source_stage": "趋势启动", "return_20": -0.06, "tags": ["trend_false_positive"], "attribution_hypotheses": ["h"]},
                      {"symbol": "MSFT", "date": "2026-10-01", "source_stage": "趋势启动", "return_20": -0.01, "tags": []}]}},
       "method": {"methods": [{"method": "M", "failure_examples": [{"symbol": "MSFT", "event_id": "x", "author": "BrightLine"}]}]}}
before = copy.deepcopy(mem)
out = xp.build("MSFT", "bullish", "2026-10-09", mem)
assert mem == before, "inputs must not be mutated"
assert out["used_in_decision"] is False and out["experience_input_status"] == "used"
ids = {p["case_id"] for p in out["precedents"]}
assert ids == {"NVDA:2026-05-08:二次启动", "AMD:2025-01-02:二次启动"}, ids
ex = {e.get("case_id"): e["why_excluded"] for e in out["excluded"]}
assert "non-equity" in ex["VIX:2026-03-24:二次启动"] and "not matured" in ex["TSLA:2026-09-01:二次启动"]
assert "look-ahead" in ex["GOOG:2026-08-20:二次启动"]                         # 60 sessions from 08-20 end after 10-09
assert "#205" in ex["method:M:x"]                                           # unverified author data never used
sides = {p["case_id"]: p["supports_or_conflicts"] for p in out["precedents"]}
assert sides["NVDA:2026-05-08:二次启动"] == "supports" and sides["AMD:2025-01-02:二次启动"] == "conflicts"
assert all(p["memory_sha256"] == "L" * 64 for p in out["precedents"])
ea = out["error_attribution"]
assert [c["case_id"] for c in ea["symbol_cases"]] == ["MSFT:2026-08-03:趋势启动"]  # 10-01 window not closed
assert ea["base_rates"]["review_samples"] == 197
# neutral stance → context only; unknown symbol → none; missing memory → unknown; future memory → excluded
assert all(p["supports_or_conflicts"] == "context" for p in xp.build("MSFT", "neutral", "2026-10-09", mem)["precedents"])
assert xp.build("ZZZZ", "neutral", "2026-10-09", mem)["experience_input_status"] == "none"
assert xp.build("MSFT", "neutral", "2026-10-09", {})["experience_input_status"] == "unknown"
fut = xp.build("MSFT", "bullish", "2026-10-08", mem)
assert not fut["precedents"] and any("look-ahead" in e["why_excluded"] for e in fut["excluded"])
# the research job attaches experience after the stance is decided and never feeds it back
src = (Path(__file__).resolve().parents[1] / "scripts" / "daily_research_job.py").read_text()
i_stance = src.index('res, m = analyse('); i_xp = src.index('xp.build(sym, res["stance"]')
assert i_xp > i_stance and 'res["stance"] =' not in src[i_xp:], "experience must not modify the stance"
print("test_experience_inputs OK")
