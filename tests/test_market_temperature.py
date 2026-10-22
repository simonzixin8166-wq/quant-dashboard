"""市场温度 v2: percentile-vs-trailing-year scale, fixed-scale fallback (labelled), missing → unavailable,
≥4/6 rule, append-only history with raw readings."""
import io, sys, zipfile
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

days = [f"{y}-{m:02d}-{d:02d}" for y in (2025, 2026) for m in range(1, 13) for d in range(1, 29)][:500]
flat = lambda v: [(d, v) for d in days]
breadth = {"as_of": days[-1], "metrics": {"new_high_52w_pct": 0.03, "new_low_52w_pct": 0.03, "b50": 0.5}}
cross = {"signals": [{"key": "credit_widening", "value": {"latest": 3.0, "date": days[-1], "chg20": 0.0}}]}

# flat market: percentile components sit at the mid-rank (50); history-less components use the fixed scale
out = mt.build(zip_of({"spy": flat(100.0), "vix": flat(20.0), "tlt": flat(90.0)}), breadth, cross)
c = {x["key"]: x for x in out["components"]}
assert out["components_available"] == 6 and out["score"] == 50.0 and out["label"] == "中性", out
assert {k for k, x in c.items() if x["method"] == "percentile_252"} == {"momentum", "volatility", "safe_haven"}
assert {k for k, x in c.items() if x["method"] == "fixed_scale"} == {"strength", "breadth", "credit"}
assert out["version"] == 3 and out["fixed_scale_components"] == 3 and isinstance(out["score"], int) and out["validated"] is False and "不是 CNN" in out["note"]

# relative scale: a rising market whose latest gain is the smallest of the year reads as fear, not greed
rising = [(d, 100.0 * 1.002 ** i) for i, d in enumerate(days[:-1])] + [(days[-1], 100.0 * 1.002 ** (len(days) - 2))]
o2 = {x["key"]: x for x in mt.build(zip_of({"spy": rising, "vix": flat(20.0)[:-1] + [(days[-1], 30.0)], "tlt": flat(90.0)}), breadth, cross)["components"]}
assert o2["momentum"]["raw"] > 0 and o2["momentum"]["score"] < 10          # above its average, yet unusually weak
assert o2["volatility"]["score"] < 5                                         # VIX spike → near-zero (inverted)

# fixed-scale fallback moves to percentile once 252 past raw readings exist in history
hist = [{"as_of": f"2024-{i:04d}", "raw": {"strength": 0.10, "breadth": 0.9, "credit": -0.2}} for i in range(252)]
o3 = {x["key"]: x for x in mt.build(zip_of({"spy": flat(100.0), "vix": flat(20.0), "tlt": flat(90.0)}), breadth, cross, hist)["components"]}
assert o3["strength"]["method"] == "percentile_252" and o3["strength"]["score"] == 0.0     # 0.0 net vs a year of +10%
assert o3["credit"]["method"] == "percentile_252" and o3["credit"]["score"] == 0.0         # spreads wider than all year

# missing inputs are unavailable, never filled; fewer than 4 → no composite
o4 = mt.build(zip_of({"spy": flat(100.0)[:30]}), {}, {})
assert o4["score"] is None and o4["status"] == "unavailable" and o4["label"] == "不可用"
assert all(x["status"] == "unavailable" and x["reason"] for x in o4["components"])

# history: one row per date (same-date rerun replaces), raw readings kept; change vs ≤5 rows back
h = mt.append_history([], dict(out, as_of="2026-10-15", score=40.0))
h = mt.append_history(h, dict(out, as_of="2026-10-16", score=45.0))
h = mt.append_history(h, dict(out, as_of="2026-10-16", score=47.0))
assert [r["as_of"] for r in h] == ["2026-10-15", "2026-10-16"] and h[1]["score"] == 47.0 and set(h[1]["raw"]) == set(c)
assert mt.with_change(dict(out, as_of="2026-10-17", score=50.0), h)["change_vs"] == {"as_of": "2026-10-15", "delta": 10.0}
assert mt.append_history(h, dict(o4)) == h
assert [mt.label(x) for x in (0, 24.9, 25, 44.9, 45, 55.9, 56, 75.9, 76, 100)] == ["极度恐惧"] * 2 + ["恐惧"] * 2 + ["中性"] * 2 + ["贪婪"] * 2 + ["极度贪婪"] * 2
print("PASS market temperature v2")

# v3: an input more than 2 NYSE sessions behind the market date is excluded (never averaged in), and says why
assert mt.lag_sessions("2026-10-16", "2026-10-16") == 0 and mt.lag_sessions("2026-10-15", "2026-10-16") == 1
assert mt.lag_sessions("2026-10-09", "2026-10-16") == 5 and mt.lag_sessions(None, "2026-10-16") is None
stale_breadth = dict(breadth, as_of=days[-30])
o5 = mt.build(zip_of({"spy": flat(100.0), "vix": flat(20.0), "tlt": flat(90.0)}), stale_breadth, cross)
c5 = {x["key"]: x for x in o5["components"]}
assert c5["breadth"]["status"] == "stale" and c5["strength"]["status"] == "stale" and "不计入" in c5["breadth"]["reason"]
assert "score" not in c5["breadth"] and o5["components_available"] == 4 and o5["score"] == 50 and o5["reference_date"] == days[-1]
# too many stale inputs → no composite rather than a precise-looking number
o6 = mt.build(zip_of({"spy": flat(100.0), "vix": flat(20.0), "tlt": flat(90.0)}), stale_breadth,
              {"signals": [{"key": "credit_widening", "value": {"latest": 3.0, "date": days[-40], "chg20": 0.0}}]})
assert o6["components_available"] == 3 and o6["score"] is None and o6["status"] == "unavailable"
# history rows carry the method version so a method change is visible and reproducible
assert mt.append_history([], o5)[0]["v"] == 3
print("market temperature v3: staleness + integer + version checks passed")
