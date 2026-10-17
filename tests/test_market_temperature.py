"""市场温度: component maths, missing → unavailable (never imputed), ≥4/6 rule, append-only history."""
import io, json, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import market_temperature as mt  # noqa: E402

def zip_of(series):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for sym, rows in series.items():
            z.writestr(f"data/{sym}_us_d.csv", "Date,Open,High,Low,Close,Volume\n" + "\n".join(f"{d},0,0,0,{c},0" for d, c in rows))
    return b.getvalue()

days = [f"2026-{m:02d}-{d:02d}" for m in range(1, 11) for d in range(1, 29)][:200]
flat = lambda v: [(d, v) for d in days]
z = zip_of({"spy": flat(100.0), "vix": flat(20.0), "tlt": flat(90.0)})
breadth = {"as_of": days[-1], "metrics": {"new_high_52w_pct": 0.03, "new_low_52w_pct": 0.03, "b50": 0.5}}
cross = {"signals": [{"key": "credit_widening", "value": {"latest": 3.0, "date": days[-1], "chg20": 0.0}}]}
out = mt.build(z, breadth, cross)
# a perfectly flat market scores exactly neutral on every component
assert out["components_available"] == 6 and out["score"] == 50.0 and out["label"] == "中性", out
assert out["validated"] is False and "不是 CNN" in out["note"] and out["cnn_link"].startswith("https://www.cnn.com/")

# direction of each mapping
up = zip_of({"spy": flat(100.0)[:-1] + [(days[-1], 110.0)], "vix": flat(20.0)[:-1] + [(days[-1], 30.0)], "tlt": flat(90.0)})
o2 = {c["key"]: c for c in mt.build(up, breadth, {"signals": [{"key": "credit_widening", "value": {"chg20": 0.5, "date": days[-1]}}]})["components"]}
assert o2["momentum"]["score"] > 50 and o2["volatility"]["score"] < 50 and o2["safe_haven"]["score"] > 50 and o2["credit"]["score"] == 0.0

# missing inputs are unavailable, not filled; fewer than 4 components → no composite
o3 = mt.build(zip_of({"spy": flat(100.0)[:30]}), {}, {})
assert o3["score"] is None and o3["status"] == "unavailable" and o3["label"] == "不可用"
assert all(c["status"] == "unavailable" and c["reason"] for c in o3["components"] if c["key"] != "safe_haven" or True)

# history: one row per date, same-date rerun replaces, other days untouched; change vs ≤5 rows back
h = mt.append_history([], dict(out, as_of="2026-10-15", score=40.0))
h = mt.append_history(h, dict(out, as_of="2026-10-16", score=45.0))
h = mt.append_history(h, dict(out, as_of="2026-10-16", score=47.0))
assert [r["as_of"] for r in h] == ["2026-10-15", "2026-10-16"] and h[1]["score"] == 47.0 and h[0]["score"] == 40.0
c = mt.with_change(dict(out, as_of="2026-10-17", score=50.0), h)
assert c["change_vs"] == {"as_of": "2026-10-15", "delta": 10.0}
assert mt.append_history(h, dict(o3)) == h          # unavailable readings never enter history
assert [mt.label(x) for x in (0, 24.9, 25, 44.9, 45, 55.9, 56, 75.9, 76, 100)] == ["极度恐惧"] * 2 + ["恐惧"] * 2 + ["中性"] * 2 + ["贪婪"] * 2 + ["极度贪婪"] * 2
print("PASS market temperature")
