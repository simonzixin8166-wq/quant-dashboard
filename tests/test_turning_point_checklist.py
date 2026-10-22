"""TP-01 变盘信号清单: thresholds as the owner confirmed (#133 6307417998), unavailable never imputed,
append-only observations, one Telegram only on the change into ≥3 met. No network (SEC/FRED are mocked)."""
import io, json, sys, tempfile, zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import turning_point_checklist as tp


def zip_of(series):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for sym, rows in series.items():
            z.writestr(f"{sym.lower()}_us_d.csv", "Date,Open,High,Low,Close,Volume\n" + "\n".join(f"{d},0,0,0,{c},0" for d, c in rows))
    return b.getvalue()


days = [f"2026-10-{d:02d}" for d in range(1, 31)]
flat = [(d, 100.0) for d in days]

# --- 2 yield thresholds: <4.8 met, <5.0 near, else not met; missing → unavailable
for v, want in ((4.79, "met"), (4.8, "near"), (4.99, "near"), (5.0, "not_met"), (5.15, "not_met")):
    assert tp.yield_condition({"series": {"DGS10": {"latest": {"value": v, "date": "2026-10-19"}}}})["status"] == want, v
assert tp.yield_condition({})["status"] == "unavailable"

# --- 3 sentiment: temperature ≤25 in last 10 readings AND QQQ beat DIA over 5 sessions
up = [(d, 100.0 + i) for i, d in enumerate(days)]
z = zip_of({"QQQ": up, "DIA": flat})
hist = lambda lo: {"rows": [{"as_of": d, "score": s} for d, s in zip(days[-10:], [40] * 9 + [lo])]}
assert tp.sentiment_condition(hist(24), z)["status"] == "met"
assert tp.sentiment_condition(hist(31), z)["status"] == "near"
assert tp.sentiment_condition(hist(31), zip_of({"QQQ": flat, "DIA": up}))["status"] == "not_met"
assert tp.sentiment_condition({}, z)["status"] == "unavailable"

# --- 4 easing: daily 20-obs change < 0, monthly MoM ≤ 0; ≥3 met, 2 near; <3 readable → unavailable
def fred(dirs):
    def f(sid):
        if dirs[sid] is None:
            raise RuntimeError("down")
        if tp.EASING_SERIES[sid] == "daily":
            return [(f"d{i}", 100 + dirs[sid] * i) for i in range(30)]
        return [("2026-08-01", 100.0), ("2026-09-01", 100.0 + dirs[sid])]
    return f
ease = {"DCOILWTICO": -1, "T10YIE": -1, "PPIACO": -1, "IR": 1}
assert tp.easing_condition({}, fred(ease))[0]["status"] == "met"
assert tp.easing_condition({}, fred({**ease, "PPIACO": 1}))[0]["status"] == "near"
assert tp.easing_condition({}, fred({**ease, "PPIACO": 0}))[0]["status"] == "met", "monthly MoM of exactly 0 counts as easing"
assert tp.easing_condition({}, fred({"DCOILWTICO": -1, "T10YIE": None, "PPIACO": None, "IR": 1}))[0]["status"] == "unavailable"
# a failed series falls back to the previous run's reading (marked cached), never to an invented value
prev = {"inputs": {"easing": {"T10YIE": {"date": "2026-10-10", "change": -0.1, "easing": True}}}}
it, inputs = tp.easing_condition(prev, fred({**ease, "T10YIE": None}))
assert inputs["T10YIE"]["cached"] is True and it["status"] == "met"

# --- 1 earnings: 8-K Item 2.02 in the last 60 days; 5-session return vs QQQ from the last close before release
sub = lambda d, items="2.02,9.01", acc="2026-10-02T16:05:00.000Z": {"filings": {"recent": {"form": ["8-K"], "filingDate": [d], "items": [items], "acceptanceDateTime": [acc]}}}
assert tp.latest_earnings_filing(sub("2026-10-02"), date(2026, 10, 21))[0] == "2026-10-02"
assert tp.latest_earnings_filing(sub("2026-10-02", items="5.02"), date(2026, 10, 21)) is None
assert tp.latest_earnings_filing(sub("2026-07-01"), date(2026, 10, 21)) is None, "older than 60 days is last quarter"
qqq = [(d, 100.0) for d in days]
winner = [(d, 100.0 if d <= "2026-10-02" else 110.0) for d in days]
# 16:05Z = 12:05 ET (after the open) → base is the filing-day close, so the jump after 10-02 counts
assert tp.reaction(winner, qqq, "2026-10-02", 12.1) > 0
assert tp.reaction(winner, qqq, "2026-10-28", 12.1) is None, "fewer than 5 sessions after the release → not scored yet"
def megas(n_win, n_lose):
    syms = list(tp.MEGACAPS)
    series = {"QQQ": qqq}
    for i, s in enumerate(syms):
        series[s] = winner if i < n_win else [(d, 90.0 if d > "2026-10-02" else 100.0) for d in days] if i < n_win + n_lose else flat
    return zip_of(series), (lambda cik: sub("2026-10-02") if list(tp.MEGACAPS.values()).index(cik) < n_win + n_lose else {"filings": {"recent": {}}})
for w, l, want in ((4, 0, "met"), (3, 0, "near"), (2, 0, "waiting"), (0, 4, "not_met"), (0, 0, "waiting")):
    zz, fetch = megas(w, l)
    assert tp.earnings_condition(zz, date(2026, 10, 21), fetch)["status"] == want, (w, l)
assert tp.earnings_condition(zip_of({"QQQ": qqq}), date(2026, 10, 21), lambda cik: (_ for _ in ()).throw(RuntimeError()))["status"] == "unavailable"

# --- overall + append-only + one Telegram on the change into ≥3 met
assert tp.overall([{"status": "met"}] * 3 + [{"status": "not_met"}])["triggered"] is True
o = tp.overall([{"status": "met"}, {"status": "near"}, {"status": "not_met"}, {"status": "unavailable"}])
assert o["met"] == 1 and o["near"] == 1 and not o["triggered"] and "继续按原计划" in o["action"]

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    tp.OUT, tp.OBS, tp.ARCHIVE = td / "out.json", td / "obs.jsonl", td / "a.zip"
    tp.MACRO, tp.TEMP_HIST = td / "macro.json", td / "temp.json"
    zz, sec = megas(4, 0)
    tp.ARCHIVE.write_bytes(zip_of({**{s: winner for s in tp.MEGACAPS}, "QQQ": up, "DIA": flat}))
    tp.MACRO.write_text(json.dumps({"series": {"DGS10": {"latest": {"value": 4.7, "date": "2026-10-29"}}}}))
    tp.TEMP_HIST.write_text(json.dumps(hist(31)))
    sent = []
    send = lambda text: sent.append(text) or "sent"
    now = datetime(2026, 10, 31, 1, tzinfo=timezone.utc)
    out = tp.build(now, sec, fred(ease), send)
    assert out["summary"]["met"] == 3 and out["summary"]["triggered"] and out["delivery"] == "sent" and len(sent) == 1
    assert "不是买卖信号" in sent[0] and out["validated"] is False and out["production_use"] is False
    tp.OUT.write_text(json.dumps(out))
    out2 = tp.build(now, sec, fred(ease), send)
    assert out2["delivery"] == "not_needed" and len(sent) == 1, "no repeat alert while the state holds"
    rows = [json.loads(l) for l in tp.OBS.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["trigger"] is True and rows[0]["market_date"] == "2026-10-30" and rows[0]["qqq_close"] == up[-1][1], rows
print("PASS TP-01 turning-point checklist: thresholds, unavailable-not-imputed, append-only, single alert on state change")
