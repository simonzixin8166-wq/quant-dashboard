from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from opportunity_strategy import decide_tqqq_state, build_leaps_radar, build_leverage_rebound_signal, merge_alert_history


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


# V6.8.2 rebound context: no material drawdown => no alert.
flat_rows=[{"datetime":f"2026-{1+i//28:02d}-{1+i%28:02d}","close":100+i*.2} for i in range(240)]
flat_vix=[{"datetime":x["datetime"],"close":16} for x in flat_rows]
inactive=build_leverage_rebound_signal(flat_rows,flat_vix,{"available":True,"status_label":"X2目标敞口","action":"保持"},radar,{"b20":.55,"b50":.55,"slope_10d":.05})
assert inactive["status"]=="inactive"
assert inactive["trigger_8"] is False

# 12%+ correction with repair should enter a comparison window, never an order.
reb=[]
for i in range(240):
    if i<220: close=100+i*.25
    elif i<232: close=155-(i-220)*2.7
    else: close=122+(i-232)*2.0
    reb.append({"datetime":f"2026-{1+i//28:02d}-{1+i%28:02d}","close":close})
reb_vix=[{"datetime":x["datetime"],"close":18 if i>231 else 24} for i,x in enumerate(reb)]
sig=build_leverage_rebound_signal(reb,reb_vix,{"available":True,"status_label":"部分敞口","action":"恢复部分敞口"},radar,{"b20":.45,"b50":.44,"slope_10d":.08})
assert sig["available"] is True
assert sig["trigger_10"] is True
assert sig["status"] in {"watch","candidate","risk"}
assert "不修改TQQQ X2" in sig["guardrail"]
assert sig["source_method"]["author"].startswith("lionhill")
