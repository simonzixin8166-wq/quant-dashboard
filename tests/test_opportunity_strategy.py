from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from opportunity_strategy import decide_tqqq_state, build_leaps_radar, merge_alert_history


target, rule, _ = decide_tqqq_state(67, {"hard_exit": True, "full_restore": True})
assert (target, rule) == (0, "hard_exit")

target, rule, _ = decide_tqqq_state(67, {"tier2": True, "tier1": True})
assert (target, rule) == (0, "tier2")

target, rule, _ = decide_tqqq_state(67, {"tier1": True})
assert (target, rule) == (33, "tier1")

target, rule, _ = decide_tqqq_state(0, {"oversold_restore": True})
assert (target, rule) == (33, "partial_restore")

target, rule, _ = decide_tqqq_state(33, {"full_restore": True})
assert (target, rule) == (67, "full_restore")

target, rule, _ = decide_tqqq_state(0, {})
assert (target, rule) == (0, "hold")

rows = []
for i in range(240):
    # Latest close is depressed enough to trigger a candidate/strong setup.
    close = 100 + i * .15 if i < 225 else 133 - (i - 225) * 1.2
    rows.append({"datetime": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "close": close})

radar = build_leaps_radar({"QQQ": rows, "SMH": rows, "VGT": rows}, 22)
assert radar["risk_limits"] == {"single_pct": .01, "total_pct": .03}
assert all(row["available"] for row in radar["assets"])
assert all(row["status"] in {"watch", "candidate", "strong"} for row in radar["assets"])

history = merge_alert_history([], {"available": True, "changed": True, "target_position": 0, "date": "2026-09-25", "action": "硬退出"}, radar)
assert any(row["kind"] == "TQQQ_X2" for row in history)
assert len({(x["date"], x["kind"], x["symbol"]) for x in history}) == len(history)

print("test_opportunity_strategy.py: all assertions passed")
