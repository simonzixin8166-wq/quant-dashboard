"""Paper simulation of the forum QQQ/TQQQ 200-day strategy (Owner 2026-11-25): signal at each close, filled at the
next session's open; first signal = the 11/24 close (80% QQQ), account opens at the 11/25 open; rules on synthetic
prices; one row per session; back end only, never an order."""
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

assert sim.SIGNAL_FROM == "2026-11-24"
assert sim.ratchet_weight(-0.1064) == 0.8 and sim.ratchet_weight(-0.0099) == 0.0 and sim.ratchet_weight(-0.2) == 1.0

# synthetic history: 220 flat days at 100, then a path; opens = previous close + 1 (so fills differ from closes)
days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(260)]
path = [100.0] * 220 + [101, 99, 96, 93, 95, 88, 92, 101, 103, 120, 121, 118, 133, 134, 99, 98] + [98] * 24
qqq, tqqq, qo, to = {}, {}, {}, {}
t = 100.0
for i, (d, p) in enumerate(zip(days, path)):
    if i:
        t *= 1 + 3 * (p / path[i - 1] - 1)
    qqq[d], tqqq[d] = p, t
    qo[d], to[d] = (path[i - 1] if i else p) + 1, t
NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)
sim.SIGNAL_FROM = days[220]
st, rows = sim.run(qqq, tqqq, qo, to, None, NOW)
by = {r["date"]: r for r in rows}
r = lambda k: by[days[k]]  # noqa: E731
w = lambda k: r(k)["holding_at_close"]["qqq_usd"] / r(k)["value"]  # noqa: E731
assert r(220)["kind"] == "first_signal" and r(220)["next_open_target"] == {"qqq": 0.0, "tqqq": 1.0}   # 101 > avg
assert st["started"] == days[221] and r(221)["filled_at_open"]["signal_date"] == days[220]          # next open
assert r(221)["filled_at_open"]["trade"]["tqqq_usd"] > 4990                                           # TQQQ bought at open
assert r(222)["filled_at_open"]["trade"]["tqqq_usd"] < 0 and abs(w(222) - 0.08) < 0.01               # 99 close -> 8% next open
assert abs(w(223) - 0.24) < 0.02                                                                      # 96 -> 24%
assert abs(w(226) - 0.88) < 0.03                                                                      # 88 (day 225) -> 88% at 226 open
assert r(227)["filled_at_open"]["trade"] is None or r(227)["filled_at_open"]["trade"]["qqq_usd"] >= 0  # bounce: buy only
assert r(228)["holding_at_close"]["tqqq_usd"] > 0 and r(228)["holding_at_close"]["qqq_usd"] == 0      # 101 (227) -> TQQQ
assert r(229)["reason"].startswith("take profit") and r(230)["holding_at_close"]["tqqq_usd"] == 0      # 120 -> cash next open
assert r(231)["holding_at_close"]["tqqq_usd"] == 0 and r(232)["reason"].startswith("re-enter")          # 133 > 1.10 x 120
assert r(233)["holding_at_close"]["tqqq_usd"] > 0 and r(235)["holding_at_close"]["tqqq_usd"] == 0      # 99 (234) -> out
assert rows[-1]["benchmark_qqq_value"] == round(5000 * (1 - sim.COST) / qo[days[221]] * 98, 2)       # bought at 11/25 open
print("PASS sim rules: signal at close, filled at the next open; TQQQ above, buy-only QQQ ratchet below, 1.15 take-profit, +10% re-entry")

# real-world opening: first signal = deepest close since the cross; one row per session (idempotent)
q2 = {d: 100.0 for d in days[:220]}
q2.update({days[220]: 99.0, days[221]: 89.0, days[222]: 94.0, days[223]: 95.0})
t2 = {d: 50.0 for d in q2}
o2 = dict(q2); o2[days[223]] = 93.0
sim.SIGNAL_FROM = days[222]
st2, rows2 = sim.run(q2, t2, o2, dict(t2), None, NOW)
assert rows2[0]["kind"] == "first_signal" and rows2[0]["next_open_target"]["qqq"] == 0.8               # deepest -10.9%
assert st2["started"] == days[223] and abs(rows2[1]["holding_at_close"]["qqq_usd"] - 4000 * 95 / 93 * (1 - sim.COST)) < 2
st3, rows3 = sim.run(q2, t2, o2, dict(t2), st2, NOW)
assert rows3 == [] and st3["last_day"] == days[223]
print("PASS sim start: first signal from the deepest close since the cross, 5,000 USD invested at the next open")

# band2 comparison account: a one-day poke above the average does not switch; 2% beyond it does
q3 = {d: 100.0 for d in days[:220]}
seq = [95, 100.5, 99, 101, 103, 102, 97.5, 97]          # below; +0.5% (no switch); -1%; +1%; +3% -> TQQQ; ...; -2.5% -> out
for k, p in enumerate(seq):
    q3[days[220 + k]] = p
t3 = {d: 50.0 for d in q3}
sim.SIGNAL_FROM = days[220]
_, ro = sim.run(q3, t3, dict(q3), dict(t3), None, NOW, 0.0)
_, rb = sim.run(q3, t3, dict(q3), dict(t3), None, NOW, 0.02)
tgt = lambda rows, k: next(x for x in rows if x["date"] == days[220 + k])["next_open_target"]["tqqq"]  # noqa: E731
assert tgt(ro, 1) == 1.0 and tgt(rb, 1) == 0.0          # +0.5%: original switches, band waits
assert tgt(ro, 3) == 1.0 and tgt(rb, 3) == 0.0          # +1%
assert tgt(rb, 4) == 1.0 and tgt(rb, 5) == 1.0          # +3% -> band switches, +2% stays (hysteresis)
assert tgt(rb, 6) == 0.0                                # -2.5% -> band sells
print("PASS sim band2: switches only 2% beyond the average, keeps its side inside the band")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    zp = tmp / "a.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for name, cl, op in (("qqq_us_d.csv", q2, o2), ("tqqq_us_d.csv", t2, t2)):
            b = io.StringIO(); wr = csv.writer(b); wr.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            for d in sorted(cl):
                wr.writerow([d, op[d], cl[d], cl[d], cl[d], 1])
            z.writestr(name, b.getvalue())
    sim.ARCHIVE, sim.OUT_DIR = zp, tmp / "sim"
    sim.STATE, sim.LEDGER = sim.OUT_DIR / "s.json", sim.OUT_DIR / "l.jsonl"
    orig = sim.load_bars
    sim.load_bars = lambda archive=zp: orig(zp)
    sim.PUBLIC = tmp / "docs" / "sim_tqqq_ma200.json"
    sim.SIGNAL_FROM = days[222]
    assert sim.main() == 0 and sim.main() == 0
    doc = json.loads(sim.STATE.read_text())
    assert doc["paper_only"] is True and doc["orders_placed"] is False and set(doc["accounts"]) == {"original", "band2"}
    assert len(sim.LEDGER.read_text().splitlines()) == 4                                  # 2 rows x 2 accounts, once
    assert all(a["summary"]["status"] == "running" for a in doc["accounts"].values())
    card = json.loads(sim.PUBLIC.read_text())
    assert card["paper_only"] and card["orders_placed"] is False and card["benchmark"]["value"] is not None
    assert set(card["accounts"]) == {"original", "band2"} and "account" not in json.dumps(card["accounts"]["original"]).replace("accounts", "")
src = (ROOT / "scripts" / "sim_tqqq_ma200.py").read_text(encoding="utf-8")
assert "requests" not in src and "import ib" not in src and "schwab" not in src.lower()
assert str(sim.LEDGER).find("/docs/") == -1                                              # the ledger stays back end
daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
assert "python scripts/sim_tqqq_ma200.py" in daily and "git add research/sim/" in daily
print("PASS sim files: ledger back end, homepage card file with paper values only, wired into Daily")
