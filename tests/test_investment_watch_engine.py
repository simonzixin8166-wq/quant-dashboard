"""V6.11 Investment Watch: gold staged-buying rules, alert de-dup, DCA calendar and reminders."""
import json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import investment_watch_engine as e  # noqa: E402

CFG = json.loads((ROOT / "config/gold_etf_long_term_watch.json").read_text(encoding="utf-8"))
DCA = json.loads((ROOT / "config/monthly_dca_plan.json").read_text(encoding="utf-8"))


def bars(closes, start=date(2026, 9, 1), lows=None, highs=None):
    out, d = [], start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append({"date": d.isoformat(), "close": c,
                    "low": (lows[i] if lows else c - 10), "high": (highs[i] if highs else c + 10)})
        d += timedelta(days=1)
    return out


def flat_macro(n=12, ry=1.80, dxy=100.0):
    rows = bars([dxy] * n)
    return [{"date": r["date"], "value": ry} for r in rows], rows


RY, DXY = flat_macro()
# Stabilising bars inside the plan: higher lows and a close above SMA5.
STABLE = bars([4060, 4050, 4040, 4030, 4025, 4030, 4040], lows=[4040, 4030, 4020, 4010, 4012, 4015, 4020])
FALLING = bars([4100, 4080, 4060, 4040, 4030, 4020, 4010], lows=[4090, 4070, 4050, 4030, 4020, 4010, 4000])

# 1. Price path 4100 → 4050 → 4020 → 3950: WAIT → WATCH(stage1) → WATCH/BUY → stage 2 (3950 lies in [3950,4000)).
assert e.decide(4100, "LIVE", STABLE, RY, DXY, CFG)["state"] == "WAIT"
d4050 = e.decide(4050, "LIVE", FALLING, RY, DXY, CFG)
assert d4050["state"] == "WATCH" and d4050["stage"] == 1 and d4050["zone"] == "core_watch", d4050
d4020_watch = e.decide(4020, "LIVE", FALLING, RY, DXY, CFG)
assert d4020_watch["state"] == "WATCH" and any("止跌" in b for b in d4020_watch["blockers"])
d4020_buy = e.decide(4020, "LIVE", STABLE, RY, DXY, CFG)
assert d4020_buy["state"] == "BUY" and d4020_buy["stage"] == 1 and d4020_buy["stage_budget_pct"] == 10, d4020_buy
d3950 = e.decide(3950, "LIVE", STABLE, RY, DXY, CFG)
assert d3950["stage"] == 2 and d3950["stage_budget_pct"] == 25
assert e.decide(3900, "LIVE", STABLE, RY, DXY, CFG)["stage"] == 3
assert e.decide(3700, "LIVE", STABLE, RY, DXY, CFG)["stage"] == 4
assert e.decide(3600, "LIVE", STABLE, RY, DXY, CFG)["state"] == "REVIEW"
assert e.decide(4300, "LIVE", STABLE, RY, DXY, CFG)["review_kind"] == "BREAKOUT_REVIEW"
assert e.next_band(1, CFG)["min"] == 3950

# 3. BUY needs open market + fresh inputs; stale data never yields BUY.
assert e.decide(4020, "CLOSED", STABLE, RY, DXY, CFG)["state"] == "WATCH"
assert e.decide(4020, "STALE", STABLE, RY, DXY, CFG)["state"] == "DATA_STALE"
assert e.decide(None, "LIVE", STABLE, RY, DXY, CFG)["state"] == "DATA_STALE"
assert e.decide(4020, "LIVE", STABLE, [], DXY, CFG, macro_fresh=False)["state"] == "WATCH"
assert e.decide(4020, "LIVE", STABLE, RY, DXY, CFG, daily_fresh=False)["state"] == "WATCH"

# 4. PAUSE (2 of 3) takes precedence over a price-confirmed BUY.
below = bars([4010, 4005, 3990, 3985, 3995, 3990, 3980], lows=[4000, 3995, 3980, 3975, 3985, 3982, 3975])
ry_up = [{"date": r["date"], "value": 1.80 + (0.05 * i if i >= 6 else 0)} for i, r in enumerate(bars([0] * 12))]
p = e.decide(3990, "LIVE", below, ry_up, DXY, CFG)
assert p["state"] == "PAUSE" and p["pause"]["met"] == 2, p["pause"]
one = e.decide(4020, "LIVE", STABLE, ry_up, DXY, CFG)
assert one["state"] == "WATCH" and one["pause"]["met"] == 1  # one risk flag blocks BUY but is not PAUSE
dxy_up = bars([100, 100, 100, 100, 100, 100, 100, 101, 101.5, 102, 102.5, 103])
assert e.pause_checks(below, RY, dxy_up, CFG)["checks"][2]["met"] is True
# Deep review: two weekly closes below 3650 + real yield worsening.
deep = bars([3640] * 12, start=date(2026, 9, 14))
dr = e.decide(3600, "LIVE", deep, ry_up, DXY, CFG)
assert dr["state"] == "REVIEW" and dr["review_kind"] == "DEEP_REVIEW"

# 2 + 5. Alert de-dup: entering once alerts once; oscillating inside does not re-alert;
# leaving above 4050+hysteresis re-arms; BUY per stage once; PAUSE on entry resets BUY.
st = None
seq = []
for price, daily in [(4100, STABLE), (4050, FALLING), (4020, FALLING), (4045, FALLING), (4030, FALLING),
                     (4020, STABLE), (4025, STABLE), (4100, STABLE), (4040, FALLING)]:
    dec = e.decide(price, "LIVE", daily, RY, DXY, CFG)
    ev, st = e.alert_events(st, dec, price, CFG)
    seq.append((price, dec["state"], ev))
assert seq[0][2] == [] and seq[1][2] == ["ENTER_WATCH_ZONE"], seq
assert seq[2][2] == [] and seq[3][2] == [] and seq[4][2] == []
assert seq[5][2] == ["BUY_CONDITIONAL"] and seq[6][2] == []  # same stage, no duplicate BUY
assert seq[8][2] == ["ENTER_WATCH_ZONE"]  # re-armed after leaving above 4070
ev, st2 = e.alert_events(st, p, 3990, CFG)
assert ev == ["PAUSE_BUYING"] and st2["buy_sent_stages"] == []
ev, _ = e.alert_events(st2, p, 3990, CFG)
assert ev == []
stale = e.decide(4020, "STALE", STABLE, RY, DXY, CFG)
assert e.alert_events(st, stale, None, CFG)[0] == []
br = e.decide(4300, "LIVE", STABLE, RY, DXY, CFG)
ev, s3 = e.alert_events(None, br, 4300, CFG)
assert ev == ["BREAKOUT_REVIEW"] and e.alert_events(s3, br, 4290, CFG)[0] == []

# Freshness classifier: weekend close is CLOSED, an old weekday quote is STALE, futures proxy is DELAYED.
fri_close = datetime(2026, 10, 9, 20, 59, tzinfo=timezone.utc)  # Fri 16:59 ET
sat = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
assert e.quote_freshness(fri_close, sat, True, CFG)[0] == "CLOSED"
wed = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
assert e.quote_freshness(wed - timedelta(minutes=5), wed, True, CFG)[0] == "LIVE"
assert e.quote_freshness(wed - timedelta(minutes=5), wed, False, CFG)[0] == "DELAYED"
assert e.quote_freshness(wed - timedelta(hours=3), wed, True, CFG)[0] == "STALE"
assert e.gold_market_open(datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc))  # Sun 19:00 ET open

# CNY/gram: 4050 × 6.703 / 31.1034768 ≈ 873; historical dates use that date's FX.
assert round(e.cny_per_gram(4050, 6.703)) == 873 and round(e.cny_per_gram(3650, 6.703)) == 787
fx = [{"date": "2026-01-29", "close": 7.10}, {"date": "2026-06-24", "close": 6.95}, {"date": "2026-10-08", "close": 6.70}]
ys = e.year_stats([], fx, 2026, CFG, price=4000)
assert ys["high"]["usdcny"] == 7.10 and ys["low"]["usdcny"] == 6.95 and ys["low_is_full_year_confirmed"] is False
assert ys["drawdown_from_high_pct"] < -28

# 6. DCA $5,000 (USD) at 4:2:4, always ordered QQQM / QLD / VGT even when jsonb reorders keys.
split = e.dca_split(5000, {"QLD": 0.2, "VGT": 0.4, "QQQM": 0.4})
assert [(x["symbol"], x["amount_usd"]) for x in split] == [("QQQM", 2000), ("QLD", 1000), ("VGT", 2000)]
assert sum(x["amount_usd"] for x in split) == 5000
msg = e.dca_message("DCA_DUE", {"amount_usd": 5000}, e.dca_window(2026, 10, DCA), split)
assert "计划 $5,000：QQQM $2,000 / QLD $1,000 / VGT $2,000" in msg and "¥" not in msg

# 7. Window: 7th–10th rolled to US sessions. 2026-11-07 is Saturday → due Mon 11-09.
w = e.dca_window(2026, 11, DCA)
assert w["due_date"] == "2026-11-09" and w["window_end"] == "2026-11-10" and w["rolled"]
w10 = e.dca_window(2026, 10, DCA)
assert w10["due_date"] == "2026-10-07" and w10["window_end"] == "2026-10-12"  # 10th is Saturday → Monday
assert e.dca_window(2027, 3, DCA)["due_date"] == "2027-03-08"  # Sun 7th → Mon 8th
assert len(e.dca_calendar(date(2026, 12, 20), DCA)) == 3 and e.dca_calendar(date(2026, 12, 20), DCA)[1]["month"] == "2027-01"

# 8. Reminder events by status; one plan per month is enforced by the DB unique key.
pend = {"status": "pending", "notified_events": []}
assert e.dca_events(pend, w10, date(2026, 10, 6)) == []
assert e.dca_events(pend, w10, date(2026, 10, 7)) == ["DCA_DUE"]
sent = {"status": "pending", "notified_events": ["DCA_DUE"]}
assert e.dca_events(sent, w10, date(2026, 10, 8)) == ["DCA_PENDING:2026-10-08"]
assert e.dca_events({**sent, "notified_events": ["DCA_DUE", "DCA_PENDING:2026-10-08"]}, w10, date(2026, 10, 8)) == []
assert e.dca_events(sent, w10, date(2026, 10, 10)) == []  # Saturday: no reminder
assert e.dca_events(sent, w10, date(2026, 10, 13)) == []  # after the window
assert e.dca_events({"status": "partial", "notified_events": ["DCA_DUE"]}, w10, date(2026, 10, 8)) == ["DCA_PARTIAL"]
assert e.dca_events({"status": "completed", "notified_events": ["DCA_DUE"]}, w10, date(2026, 10, 8)) == ["DCA_COMPLETED"]
assert e.dca_events({"status": "completed", "notified_events": ["DCA_COMPLETED"]}, w10, date(2026, 10, 9)) == []
assert e.dca_events({"status": "skipped", "notified_events": []}, w10, date(2026, 10, 8)) == ["DCA_SKIPPED"]

# Journal: state entries only; observation vs scoreable prediction are separate; outcomes need
# completed sessions anchored on the 17:00 ET gold session; proxy daily → never "verified".
rows = []
dec = e.decide(4020, "LIVE", STABLE, RY, DXY, CFG)
assert dec["state"] == "BUY"
assert e.should_journal(rows, dec)
t0 = datetime(2026, 9, 1, 15, tzinfo=timezone.utc)  # Tue 11:00 ET → session 2026-09-01
rows.append(e.journal_entry(dec, {"price": 4020, "basis": "spot", "source": "t", "as_of": "x"}, t0, CFG, "LIVE", "spot"))
assert not e.should_journal(rows, dec) and not e.should_journal(rows, stale)
r0 = rows[0]
assert r0["schema"] == 2 and r0["capture_mode"] == "live_observation" and r0["session_date"] == "2026-09-01"
assert r0["observation_eligible"] and r0["scoreable"] and r0["claim"] == "forward_return_positive"
assert "budget" not in json.dumps(r0)
watch = e.journal_entry(e.decide(4020, "LIVE", FALLING, RY, DXY, CFG), {"price": 4020, "basis": "spot"}, t0, CFG, "LIVE", "spot")
assert watch["observation_eligible"] and not watch["scoreable"] and not watch["forward_evidence_eligible"]
closed = e.journal_entry(dec, {"price": 4020, "basis": "spot"}, t0, CFG, "CLOSED", "spot")
assert not closed["observation_eligible"] and not closed["scoreable"]
proxyq = e.journal_entry(dec, {"price": 4020, "basis": "futures_proxy"}, t0, CFG, "DELAYED", "spot")
assert not proxyq["scoreable"]
# 17:00 ET roll: Fri 18:00 ET belongs to Monday's session.
assert e.gold_session_date(datetime(2026, 9, 4, 22, tzinfo=timezone.utc)).isoformat() == "2026-09-07"
long = bars([4020 + i for i in range(130)], start=date(2026, 9, 1))
oc = e.evaluate_outcomes(rows, long, "spot")[0]
assert oc["mature_20d"] and oc["verified_20d"] and oc["mature_120d"] and oc["ret_20d_pct"] > 0
assert oc["horizon_20d_date"] == long[20]["date"]  # anchor = signal session (idx 0) → h-th completed after it
assert not e.evaluate_outcomes(rows, long[:30], "spot")[0]["mature_60d"]
px = e.evaluate_outcomes(rows, long, "spot_estimate_from_futures")[0]
assert px["mature_20d"] and not px["verified_20d"] and px["outcome_basis"] == "proxy_estimate_unverified"
# Missing entry session (data hole) → no anchor rather than a shifted one.
gap = [r for r in long if r["date"] >= "2026-09-10"]
assert e.evaluate_outcomes(rows, gap, "spot")[0].get("anchor_issue") == "entry_session_missing"
# Legacy schema-1 WAIT row (already in production) is read as observation-only, never rewritten.
legacy = {"capture_mode": "live_forward", "forward_evidence_eligible": True, "price": 4121.1, "price_basis": "spot",
          "recorded_at": "2026-10-08T07:34:09Z", "signal_id": "7604e4a7e0881413", "state": "WAIT", "state_key": "WAIT|None|None"}
assert e.journal_flags(legacy) == (True, False, "2026-10-08")
summ = e.learning_summary([legacy] + rows, e.evaluate_outcomes([legacy] + rows, long, "spot_estimate_from_futures"))
assert summ["scoreable_predictions"] == 1 and summ["verified_scoreable"]["20d"] == 0 and summ["mature_any"]["20d"] == 2

# Date-aware macro windows: a data hole is not compressed into a "5-day" change.
holey = [{"date": d, "value": v} for d, v in [("2026-09-01", 1.0), ("2026-09-02", 1.0), ("2026-09-03", 1.0),
                                                ("2026-09-04", 1.0), ("2026-09-18", 1.5), ("2026-09-21", 1.6)]]
assert e.window_change(holey, "value", 5) is None
assert e.window_change(RY, "value", 5) == 0.0
assert e.consecutive_sessions(STABLE, 2) and not e.consecutive_sessions([{"date": "2026-09-01"}, {"date": "2026-09-15"}], 2)
pc_hole = e.pause_checks(STABLE, holey, DXY, CFG)
assert pc_hole["checks"][1]["met"] is None

# Public status never carries budget/DCA amounts.
data = {"live": {"ok": True, "price": 4020.0, "as_of": e.iso(wed - timedelta(minutes=3)), "source": "t",
                 "basis": "spot", "realtime": True},
        "daily": {"ok": True, "rows": bars([4060, 4050, 4040, 4030, 4025, 4030, 4040], start=date(2026, 9, 28),
                                           lows=[4040, 4030, 4020, 4010, 4012, 4015, 4020]), "source": "t", "basis": "spot"},
        "real_yield": {"ok": True, "rows": [{"date": r["date"], "value": 1.8} for r in bars([0] * 12, start=date(2026, 9, 21))]},
        "dxy": {"ok": True, "rows": bars([100] * 12, start=date(2026, 9, 21))},
        "fx": {"ok": True, "rows": fx, "live": 6.70, "live_at": "2026-10-07"}, "etf": {}}
status, dec, ev = e.build_status(data, CFG, DCA, {}, wed)
assert status["gold"]["state"] == "BUY" and ev == ["ENTER_WATCH_ZONE", "BUY_CONDITIONAL"], (status["gold"]["state"], ev)
txt = json.dumps(status, ensure_ascii=False)
assert "amount" not in txt and "5000" not in txt and "budget_usd" not in txt
data["live"]["basis"] = "futures_proxy"
assert e.build_status(data, CFG, DCA, {}, wed)[0]["gold"]["state"] == "WATCH"
data["live"]["basis"] = "spot"; data["fx"] = {"ok": False, "rows": []}
assert e.build_status(data, CFG, DCA, {}, wed)[0]["gold"]["state"] == "DATA_STALE"

print("PASS V6.11 investment watch: gold rules/dedup/freshness/CNY + DCA calendar/reminders/journal")

# Futures daily bars are shifted by the measured futures−spot basis; implausible basis keeps the raw proxy.
fut = {"ok": True, "basis": "futures_proxy", "source": "f", "rows": [{"date": "2026-10-07", "close": 4030.0, "high": 4040.0, "low": 4020.0}]}
adj = e.basis_adjust(fut, {"basis": "spot", "price": 4000.0}, futures_now=4025.0)
assert adj["basis"] == "spot_estimate_from_futures" and adj["rows"][0]["close"] == 4005.0 and adj["futures_spot_basis"] == 25.0
assert e.basis_adjust(fut, {"basis": "spot", "price": 4000.0}, futures_now=4400.0)["basis"] == "futures_proxy"
assert e.basis_adjust(fut, {"basis": "futures_proxy", "price": 4000.0}, futures_now=4025.0) is fut
print("PASS basis adjustment")

# Year stats: verified provenance low wins over a futures estimate; later estimate is labelled separately.
est_rows = [{"date": "2026-06-30", "close": 3940.0, "high": 3950.0, "low": 3932.0}, {"date": "2026-10-07", "close": 4120.0, "high": 4130.0, "low": 4100.0}]
ys2 = e.year_stats(est_rows, fx, 2026, CFG, price=4126, basis="spot_estimate_from_futures")
assert ys2["low"]["value"] == 3959.33 and ys2["low"]["verified"] and ys2["low_estimate_after_verified"]["value"] == 3932.0
assert ys2["high"]["value"] == 5595.47
print("PASS year stats provenance")

# Telegram text: amounts only from the private budget; no budget → explicitly no amount.
d_buy = e.decide(4020, "LIVE", STABLE, RY, DXY, CFG)
m1 = e.gold_message("BUY_CONDITIONAL", d_buy, {"price": 4020.0, "source": "t", "as_of": "x"}, CFG, {}, None)
assert "不输出建议金额" in m1 and "下一档观察：$4,000–3,950" in m1
m2 = e.gold_message("BUY_CONDITIONAL", d_buy, {"price": 4020.0, "source": "t", "as_of": "x"}, CFG, {}, {"budget": 20000, "spent": 2000, "stages": [1]})
assert "≈ $2,000" in m2 and "不重复扣减" in m2
print("PASS telegram text")

# Source-quality gate: LIVE spot + estimated daily + macro OK + confirmation OK must NOT be BUY.
def _with_daily_basis(basis):
    d2 = json.loads(json.dumps(data)); d2["daily"]["basis"] = basis
    d2["live"]["basis"] = "spot"; d2["fx"] = {"ok": True, "rows": fx, "live": 6.70, "live_at": "2026-10-07"}
    return e.build_status(d2, CFG, DCA, {}, wed)
st_spot, _, ev_spot = _with_daily_basis("spot")
assert st_spot["gold"]["state"] == "BUY" and st_spot["gold"]["buy_data_gate"]["trusted_spot_daily"] is True
for basis in ("spot_estimate_from_futures", "futures_proxy", None):
    st_x, dec_x, ev_x = _with_daily_basis(basis)
    g = st_x["gold"]
    assert g["state"] == "WATCH", (basis, g["state"])
    assert g["buy_data_gate"]["trusted_spot_daily"] is False and g["buy_data_gate"].get("downgraded_buy") is True
    assert any("可信现货日线" in b for b in g["blockers"])
    assert "BUY_CONDITIONAL" not in ev_x and "ENTER_WATCH_ZONE" in ev_x
# Risk states are not masked by the gate: PAUSE still PAUSE on estimated bars.
d3 = json.loads(json.dumps(data)); d3["daily"]["basis"] = "spot_estimate_from_futures"
d3["fx"] = {"ok": True, "rows": fx, "live": 6.70, "live_at": "2026-10-07"}
d3["live"]["price"] = 3990.0
d3["daily"]["rows"] = [dict(r, close=c, low=c - 10) for r, c in zip(d3["daily"]["rows"], [4010, 4005, 3990, 3985, 3995, 3990, 3980])]
d3["real_yield"]["rows"] = [dict(r, value=1.8 + (0.05 * i if i >= 6 else 0)) for i, r in enumerate(d3["real_yield"]["rows"])]
assert e.build_status(d3, CFG, DCA, {}, wed)[0]["gold"]["state"] == "PAUSE"
# Implausible basis (contract roll / reversal) leaves raw futures_proxy → still no BUY.
assert e.basis_adjust(fut, {"basis": "spot", "price": 4000.0}, futures_now=3700.0)["basis"] == "futures_proxy"
print("PASS gold BUY source-quality gate")
