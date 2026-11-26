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
f221 = r(221)["filled_at_open"]["fills"]
assert len(f221) == 1 and f221[0]["side"] == "BUY" and f221[0]["symbol"] == "TQQQ" and f221[0]["price"] == round(to[days[221]], 2)
assert f221[0]["shares"] * f221[0]["price"] + f221[0]["commission"] <= 5000 and f221[0]["commission"] == 1.0   # whole shares
f222 = r(222)["filled_at_open"]["fills"]
assert [x["side"] for x in f222][0] == "SELL" and f222[0]["symbol"] == "TQQQ" and "realized_pnl" in f222[0]    # sell first
assert abs(w(222) - 0.08) < 0.03                                                                      # 99 close -> 8% next open
assert abs(w(223) - 0.24) < 0.02                                                                      # 96 -> 24%
assert abs(w(226) - 0.88) < 0.04                                                                      # 88 (day 225) -> 88% at 226 open
assert all(x["side"] == "BUY" for x in r(227)["filled_at_open"]["fills"])                             # bounce: buy only
assert r(228)["holding_at_close"]["tqqq_usd"] > 0 and r(228)["holding_at_close"]["qqq_usd"] == 0      # 101 (227) -> TQQQ
assert r(229)["reason"].startswith("take profit") and r(230)["holding_at_close"]["tqqq_usd"] == 0      # 120 -> cash next open
assert r(231)["holding_at_close"]["tqqq_usd"] == 0 and r(232)["reason"].startswith("re-enter")          # 133 > 1.10 x 120
assert r(233)["holding_at_close"]["tqqq_usd"] > 0 and r(235)["holding_at_close"]["tqqq_usd"] == 0      # 99 (234) -> out
bsh = int((5000 - 1.0) // qo[days[221]])
assert rows[-1]["benchmark_qqq_value"] == round(bsh * 98 + (5000 - bsh * qo[days[221]] - 1.0), 2)  # whole shares at the open
assert all(set(x) >= {"date", "side", "symbol", "shares", "price", "amount", "commission"} for x in st["fills"])
assert all(isinstance(x["shares"], int) and x["shares"] > 0 for x in st["fills"])
pos = rows[-1]["positions"]; assert all(set(p) >= {"symbol", "shares", "avg_cost", "price", "market_value", "unrealized_pnl"} for p in pos)
assert sim.commission(6, 617.09) == 1.0 and sim.commission(400, 45.0) == 2.0 and sim.commission(1, 50.0) == 0.5   # IBKR fixed
assert not r(233)["reason"].startswith("take profit")                                              # 134 right after the
#   buy-back is still >= 1.15 x average, but the take-profit stays disarmed (Owner 2026-11-26)

# take-profit re-arms only after QQQ closes back under 1.15 x average
q4 = {d: 100.0 for d in days[:220]}
seq4 = [101, 116, 128, 130, 110, 120]   # TQQQ; TP at 116; buy back at 128 (>1.1x116); 130 hold; 110 re-arm; 120 TP again
for k, p in enumerate(seq4):
    q4[days[220 + k]] = p
t4 = {d: 50.0 for d in q4}
sim.SIGNAL_FROM = days[220]
_, r4 = sim.run(q4, t4, dict(q4), dict(t4), None, NOW)
why = lambda k: next(x for x in r4 if x["date"] == days[220 + k])["reason"]  # noqa: E731
assert why(1).startswith("take profit") and why(2).startswith("re-enter")
assert why(3).startswith("above") and why(4).startswith("above") and why(5).startswith("take profit")
print("PASS sim take-profit re-arm: no sell the day after a buy-back; armed again once under 1.15 x average")
sim.SIGNAL_FROM = days[220]
print("PASS sim IBKR-style: whole shares at the open, sells first, IBKR fixed commission, fill log, avg cost, realized P/L")
print("PASS sim rules: signal at close, filled at the next open; TQQQ above, buy-only QQQ ratchet below, 1.15 take-profit, +10% re-entry")

# real-world opening: first signal = deepest close since the cross; one row per session (idempotent)
q2 = {d: 100.0 for d in days[:220]}
q2.update({days[220]: 99.0, days[221]: 89.0, days[222]: 94.0, days[223]: 95.0})
t2 = {d: 50.0 for d in q2}
o2 = dict(q2); o2[days[223]] = 93.0
sim.SIGNAL_FROM = days[222]
st2, rows2 = sim.run(q2, t2, o2, dict(t2), None, NOW)
assert rows2[0]["kind"] == "first_signal" and rows2[0]["next_open_target"]["qqq"] == 0.8               # deepest -10.9%
assert st2["started"] == days[223] and rows2[1]["positions"][0]["shares"] == 43                       # floor(4000/93)
assert rows2[1]["positions"][0]["avg_cost"] == round((43 * 93 + 1.0) / 43, 2)
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

# 530 book: all-in TQQQ the open after EMA5 crosses above EMA30 of the TQQQ close, all cash after it crosses below;
# a book starts in cash until the first golden cross (the blogger's script acts only on crosses)
t5 = {d: 50.0 for d in days[:220]}
up = [50, 52, 55, 58, 60, 62, 61, 60, 57, 54, 52, 50, 49, 48, 50, 53, 56, 59]
for k, p in enumerate(up):
    t5[days[220 + k]] = float(p)
q5 = {d: 100.0 for d in t5}
sim.SIGNAL_FROM = days[219]
st5, r5 = sim.run(q5, t5, dict(q5), dict(t5), None, NOW, 0.0, "ema530")
e5s, e30s = sim.ema_series(t5, 5), sim.ema_series(t5, 30)
gold = next(d for a, d in zip(days[219:], days[220:]) if e5s[a] <= e30s[a] and e5s[d] > e30s[d])
dead = next(d for a, d in zip(days[219:], days[220:]) if d > gold and e5s[a] >= e30s[a] and e5s[d] < e30s[d])
f5 = st5["fills"]
nxt = lambda d: days[days.index(d) + 1]  # noqa: E731
assert f5[0]["side"] == "BUY" and f5[0]["symbol"] == "TQQQ" and f5[0]["date"] == nxt(gold)
assert f5[1]["side"] == "SELL" and f5[1]["date"] == nxt(dead) and all(x["symbol"] == "TQQQ" for x in f5)
print("PASS sim 530: golden cross -> all TQQQ at the next open, death cross -> all cash at the next open, TQQQ only")

# hybrid book: band2 above the average; below it, 50% TQQQ while the 530 signal is on, the QQQ ladder otherwise
q6 = {d: 100.0 for d in days[:220]}
t6 = {d: 50.0 for d in days[:220]}
path6 = [100 - 0.5 * k for k in range(1, 25)] + [88 + 0.8 * k for k in range(1, 11)] + [95, 93, 91, 89, 87, 85]
prev6 = 100.0                       # slow slide, a rally that stays under the average, then a fall; TQQQ moves 3x
for k, p in enumerate(path6):
    q6[days[220 + k]] = float(p)
    t6[days[220 + k]] = t6[days[219 + k]] * (1 + 3 * (p / prev6 - 1)); prev6 = p
sim.SIGNAL_FROM = days[220]
st6, r6 = sim.run(q6, t6, dict(q6), dict(t6), None, NOW, 0.02, "hybrid")
_, rb6 = sim.run(q6, t6, dict(q6), dict(t6), None, NOW, 0.02)
on_rows = [x for x in r6 if x["reason"].startswith("hybrid:")]
assert on_rows and all(x["next_open_target"] == {"qqq": 0.0, "tqqq": 0.5} for x in on_rows)
assert not any(x["reason"].startswith("hybrid:") for x in rb6)                        # band2 never does this
tq_buys = [x for x in st6["fills"] if x["symbol"] == "TQQQ" and x["side"] == "BUY"]
assert len(tq_buys) == 1                                                              # no daily drift top-ups at 50%
after = [x for x in r6 if x["date"] > on_rows[-1]["date"]]
assert after and after[0]["next_open_target"]["tqqq"] == 0.0 and after[0]["next_open_target"]["qqq"] > 0
print("PASS sim hybrid: below the average 50% TQQQ only while 530 is on (one buy, no drift trades), then back to the QQQ ladder")

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
    sent = []
    sim.notify = lambda text: (sent.append(text), "sent")[1]
    assert sim.main() == 0 and sim.main() == 0
    doc = json.loads(sim.STATE.read_text())
    assert doc["paper_only"] is True and doc["orders_placed"] is False and set(doc["accounts"]) == {"band2", "ema530", "hybrid"}
    assert len(sim.LEDGER.read_text().splitlines()) == 6                                  # 2 rows x 3 books, once
    assert all(a["summary"]["status"] == "running" for a in doc["accounts"].values())
    assert doc["rehearsal"]["signal_day"] == days[223] and len(sent) <= 1               # once per signal day
    card = json.loads(sim.PUBLIC.read_text())
    assert card["paper_only"] and card["orders_placed"] is False and card["benchmark"]["value"] is not None
    assert set(card["accounts"]) == {"band2", "ema530", "hybrid"} and card["order"] == ["band2", "ema530", "hybrid"]
    assert card["benchmark"]["qqq_shares"] == int((5000 - 1.0) // 93.0) and card["benchmark"]["buy_price"] == 93.0
    import privacy_canary_scan as pcs
    # owner-approved exception (2026-11-26): only the three paper-sim files, only with paper_only=true, only the
    # position_field KEY rule; elsewhere (or without the flag) the same keys still fail, and other rules still apply
    allow = pcs.load_allowlist()
    names = {"l.jsonl": "research/sim/tqqq_ma200_ledger.jsonl", "s.json": "research/sim/tqqq_ma200_state.json"}
    for f in sim.OUT_DIR.iterdir():
        out = []; pcs.scan_text(f.read_text(), names[f.name], f.suffix, allow, out); assert out == [], out
    out = []; pcs.scan_text(sim.PUBLIC.read_text(), "docs/research/sim_tqqq_ma200.json", ".json", allow, out); assert out == []
    out = []; pcs.scan_text(sim.PUBLIC.read_text(), "docs/research/other.json", ".json", allow, out)
    assert out and all(h["category"] == "position_field" for h in out)                # same content, other file: blocked
    unflagged = json.loads(sim.PUBLIC.read_text()); unflagged.pop("paper_only")
    out = []; pcs.scan_text(json.dumps(unflagged), "docs/research/sim_tqqq_ma200.json", ".json", allow, out); assert out
    leak = json.loads(sim.PUBLIC.read_text()); leak["note_zh"] = "联系 someone@realmail.net"
    out = []; pcs.scan_text(json.dumps(leak), "docs/research/sim_tqqq_ma200.json", ".json", allow, out)
    assert [h["category"] for h in out] == ["email"]                                    # other rules still apply
# rehearsal reminder (Owner 2026-11-26): plain Chinese, only books that trade, estimate at the signal close
txt = sim.rehearsal_text("2026-11-27", {"band2": ([{"side": "BUY", "symbol": "QQQ", "shares": 1}], {"w_q": 0.88, "w_t": 0}),
                                         "ema530": ([], {"w_q": 0, "w_t": 0}),
                                         "hybrid": ([{"side": "SELL", "symbol": "QQQ", "shares": 7},
                                                     {"side": "BUY", "symbol": "TQQQ", "shares": 50}], {"w_q": 0, "w_t": 0.5})})
assert "纸面" in txt and "买入 QQQ 约 1 股" in txt and "QQQ 88%，其余现金" in txt and "TQQQ 50%，其余现金" in txt
assert "530 策略" not in txt and "不需要回复" in txt
assert sim.rehearsal_text("2026-11-27", {"band2": ([], {"w_q": 0.8, "w_t": 0})}) is None
st_p = {"started": "x", "pending": {"w_q": 0.0, "w_t": 1.0}, "cash": 5000.0, "qqq_sh": 0, "tqqq_sh": 0, "positions": {}, "fills": []}
po = sim.planned_orders(st_p, "ma200", 100.0, 50.0)
assert po and po[0]["side"] == "BUY" and po[0]["symbol"] == "TQQQ" and st_p["tqqq_sh"] == 0 and st_p["fills"] == []  # on a copy
print("PASS sim rehearsal: Telegram note lists only books that trade at the next open, estimated, once per signal day")
src = (ROOT / "scripts" / "sim_tqqq_ma200.py").read_text(encoding="utf-8")
assert "requests" not in src and "import ib" not in src and "schwab" not in src.lower() and "placeOrder" not in src
assert str(sim.LEDGER).find("/docs/") == -1                                              # the ledger stays back end
daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
assert "python scripts/sim_tqqq_ma200.py" in daily and "git add research/sim/" in daily
print("PASS sim files: ledger back end, homepage card file with paper values only, wired into Daily")
