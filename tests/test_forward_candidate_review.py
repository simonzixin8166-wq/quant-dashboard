"""#133 6106619625: per-candidate checklist is proposal-only, deterministic and append-only."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_candidate_review as fcr

assert fcr.mode_invariant("趋势恶化", -50)            # never eligible, waits in both modes
assert not fcr.mode_invariant("二次启动", 40)          # eligible only in fear mode
data = {"market_indicators": {"spx": {"day_chg": -0.005}, "ixic": {"day_chg": 0.0}, "vix": {"close": 20}},
        "trend_pulse": {"ZZA": {"available": True, "date": "2026-09-29", "state": "修复中", "score": 90},
                        "ZZB": {"available": True, "date": "2026-09-29", "state": "二次启动", "score": 40}},
        "stocks": {"ZZA": {"date": "2026-09-29", "close": 10}, "ZZB": {"date": "2026-09-29", "close": 5}}}
f = {"evidence": {"commit": "c" * 40, "commit_time": "2026-09-30T00:47:22Z", "data_json_blob": "b" * 40, "rule_file_blobs": {}},
     "next_open": "2026-09-30T13:30:00Z"}
out, why, det = fcr.review_session("2026-09-29", f, {"candidate_cap": 6, "grid_cases": 1408, "diff_count": 0}, set(), data)
assert det and why == "ok" and len(out) == 2
by = {o["symbol"]: o for o in out}
assert by["ZZA"]["proposed_class"] == "historically_attested_reconstruction" and by["ZZA"]["locked_before_next_open"]
assert by["ZZB"]["proposed_class"] == "needs_evidence" and "intraday_market_mode" in by["ZZB"]["residual_dependencies"]
assert all(o["approved"] is False for o in out)
out2, _, _ = fcr.review_session("2026-09-29", f, {"candidate_cap": 6}, {"2026-09-29"}, data)
assert all(o["proposed_class"] == "already_server_forward" for o in out2)
# ledger file never carries an approval written by the tool
p = ROOT / "research/archive/forward_candidate_review.jsonl"
if p.exists():
    assert all(json.loads(l)["approved"] is False for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
print("PASS forward candidate review")
