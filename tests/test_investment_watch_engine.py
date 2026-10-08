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

# 6. DCA ¥5,000 at 4:2:4.
split = e.dca_split(5000, DCA["weights"])
assert [(x["symbol"], x["amount_cny"]) for x in split] == [("QQQM", 2000), ("QLD", 1000), ("VGT", 2000)]
assert sum(x["amount_cny"] for x in split) == 5000

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

# Journal: state entries only, live forward captures; outcomes only when mature.
rows = []
dec = e.decide(4020, "LIVE", STABLE, RY, DXY, CFG)
assert e.should_journal(rows, dec)
rows.append(e.journal_entry(dec, {"price": 4020, "basis": "spot", "source": "t", "as_of": "x"},
                            datetime(2026, 9, 1, tzinfo=timezone.utc), CFG))
assert not e.should_journal(rows, dec) and not e.should_journal(rows, stale)
assert rows[0]["capture_mode"] == "live_forward" and "budget" not in json.dumps(rows[0])
long = bars([4020 + i for i in range(130)])
oc = e.evaluate_outcomes(rows, long)[0]
assert oc["mature_20d"] and oc["mature_120d"] and oc["ret_20d_pct"] > 0
assert not e.evaluate_outcomes(rows, long[:30])[0]["mature_60d"]

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
