"""Paper simulation of the forum QQQ/TQQQ 200-day strategy (Owner 2026-11-25): rules on synthetic prices, opening
state from the deepest close since the cross, idempotent per session, back end only, never an order."""
import csv
import io
import json
import sys
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sim_tqqq_ma200 as sim  # noqa: E402

# 200-day ratchet
assert sim.ratchet_weight(-0.1064) == 0.8 and sim.ratchet_weight(-0.0099) == 0.0 and sim.ratchet_weight(-0.2) == 1.0
assert sim.ratchet_weight(0.02) == 0.0

# synthetic history: 220 flat days at 100, then a path; TQQQ moves 3x
days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(260)]
path = [100.0] * 220 + [101, 99, 96, 93, 95, 88, 92, 101, 103, 120, 121, 118, 133, 134, 99, 98] + [98] * 24
qqq, tqqq = {}, {}
t = 100.0
for i, (d, p) in enumerate(zip(days, path)):
    if i:
        t *= 1 + 3 * (p / path[i - 1] - 1)
    qqq[d], tqqq[d] = p, t
sim.START_FROM = days[220]
st, rows = sim.run(qqq, tqqq, None, datetime(2026, 11, 25, tzinfo=timezone.utc))
by = {r["date"]: r for r in rows}
r = lambda k: by[days[k]]  # noqa: E731
w0 = lambda k: r(k)["holding"]["qqq_usd"] / r(k)["value"]  # noqa: E731
assert r(220)["holding"]["tqqq_usd"] > 4990 and r(220)["reason"].startswith("above")          # 101 > avg 100
assert r(221)["holding"]["tqqq_usd"] == 0 and abs(w0(221) - 0.08) < 0.005                    # -1.0% -> 8%
assert abs(r(222)["holding"]["qqq_usd"] / r(222)["value"] - 0.24) < 0.01                       # ~-4% -> 24%
w = lambda k: r(k)["holding"]["qqq_usd"] / r(k)["value"]  # noqa: E731
assert abs(w(225) - 0.88) < 0.02                                                               # -12% -> 88%
assert w(226) >= 0.86                                                                          # bounce: buy only, no sell
assert r(227)["holding"]["tqqq_usd"] > 0 and r(227)["holding"]["qqq_usd"] == 0                 # back above -> all TQQQ
tp = r(229)
assert tp["reason"].startswith("take profit") and tp["holding"]["tqqq_usd"] == 0              # 120 >= 1.15 x avg
assert r(230)["holding"]["tqqq_usd"] == 0 and r(231)["holding"]["tqqq_usd"] == 0               # 121, 118: wait in cash
assert r(232)["reason"].startswith("re-enter") and r(232)["holding"]["tqqq_usd"] > 0            # 133 > 1.10 x 120
assert r(234)["holding"]["tqqq_usd"] == 0                                                      # 99 below avg -> out
assert all(x["trade"] is None or x["trade"]["cost"] >= 0 for x in rows)
assert rows[-1]["benchmark_qqq_value"] == round(5000 / 101 * 98, 2)
print("PASS sim rules: TQQQ above, ratchet QQQ below (buy only), 1.15 take-profit, re-entry 10% above the take-profit close")

# opening state on the real-world pattern: deepest close since the cross sets the starting QQQ weight
q2 = {d: 100.0 for d in days[:220]}
q2.update({days[220]: 99.0, days[221]: 89.0, days[222]: 94.0})
t2 = {d: 50.0 for d in q2}
sim.START_FROM = days[222]
st2, rows2 = sim.run(q2, t2, None, datetime(2026, 11, 25, tzinfo=timezone.utc))
assert abs(rows2[0]["holding"]["qqq_usd"] / rows2[0]["value"] - 0.80) < 0.01, rows2[0]                 # deepest -10.9% -> 80%
# idempotent: the same session again adds nothing
st3, rows3 = sim.run(q2, t2, st2, datetime(2026, 11, 26, tzinfo=timezone.utc))
assert rows3 == [] and st3["last_day"] == days[222]
print("PASS sim start: opening weight from the deepest close since the cross; one row per session")

# main() on a temp archive writes back-end files only
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    zp = tmp / "a.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for name, series in (("qqq_us_d.csv", q2), ("tqqq_us_d.csv", t2)):
            b = io.StringIO(); w2 = csv.writer(b); w2.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            for d in sorted(series):
                w2.writerow([d, series[d], series[d], series[d], series[d], 1])
            z.writestr(name, b.getvalue())
    sim.ARCHIVE, sim.OUT_DIR = zp, tmp / "sim"
    sim.STATE, sim.LEDGER = sim.OUT_DIR / "s.json", sim.OUT_DIR / "l.jsonl"
    orig = sim.load_closes
    sim.load_closes = lambda archive=zp: orig(zp)
    assert sim.main() == 0 and sim.main() == 0
    doc = json.loads(sim.STATE.read_text())
    assert doc["paper_only"] is True and doc["orders_placed"] is False and doc["published"] is False
    assert len(sim.LEDGER.read_text().splitlines()) == 1 and doc["summary"]["status"] == "running"
src = (ROOT / "scripts" / "sim_tqqq_ma200.py").read_text(encoding="utf-8")
assert "requests" not in src and "broker" not in src.lower().replace("no broker is contacted", "")
assert not str(sim.OUT_DIR).startswith(str(ROOT / "docs"))
daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
assert "python scripts/sim_tqqq_ma200.py" in daily and "git add research/sim/" in daily
print("PASS sim files: back end only (research/sim), paper only, wired into Daily after the archive refresh")
