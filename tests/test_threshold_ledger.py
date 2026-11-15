"""Threshold ledger: transitions follow the production alert rule (once per line per cycle, leave at line - 2 pp),
every crossing is recorded even without an alert, episodes carry values and follow-ups, the ledgers are
append-only and idempotent, a price revision appends a row, alerts are reconciled against prices (the 11/10
stale-drawdown alerts are flagged unsupported), historical replay is kept apart. Synthetic inputs, no network."""
import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import threshold_ledger as tl

TIERS = {"t1": 0.15, "t2": 0.20, "t3": 0.30}           # near = 0.13
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def bars_from(closes, start="2026-10-01"):
    d0 = date.fromisoformat(start)
    out, i = [], 0
    for c in closes:
        d = d0 + timedelta(days=i)
        while d.weekday() >= 5:
            i += 1
            d = d0 + timedelta(days=i)
        out.append((d.isoformat(), c * 1.0, c * 0.99, c * 1.0))
        i += 1
    return out


# 100 high, falls to 84 (t1), recovers to 86.5 (above 85 but not by 2 pp), back to 84.5, recovers to 88 (leave t1),
# dips to 84 again (re-touch: no alert, same cycle), then a new high 101 (new cycle), then 86.5 (near again).
closes = [100, 95, 90, 86, 84, 86.5, 84.5, 88, 84, 92, 101, 86.5] + [87] * 60
bars = bars_from(closes)
days, trans = tl.replay(bars, TIERS)
got = [(t["date"], t["kind"], t["line"]) for t in trans]
D = [b[0] for b in bars]
assert got == [(D[3], "enter", "near"), (D[4], "enter", "t1"), (D[7], "leave", "t1"), (D[11], "enter", "near")], got
assert all(t["line_value"] in (0.13, 0.15) for t in trans)
assert trans[1]["line_price"] == 85.0 and trans[1]["drawdown"] == -0.16

# every crossing, with or without an alert
tch = tl.touches(days, TIERS, D[0])
assert tch["t1"]["cross_in"] == 3 and tch["t1"]["cross_out"] == 3, tch["t1"]
assert [x["date"] for x in tch["t1"]["events"] if x["kind"] == "cross_in"] == [D[4], D[6], D[8]]
assert any(m["date"] == D[11] for m in tch["t1"]["near_misses"]) is False      # 86.5 vs 85.85: gap 0.64 pp > 0.5
assert any(m["date"] == D[12] for m in tch["t1"]["near_misses"]) is False

# episodes: values, sessions in zone, deepest, end, follow-ups
eps = tl.episodes(days, trans, TIERS)
t1 = next(e for e in eps if e["line"] == "t1")
assert t1["enter_date"] == D[4] and t1["end"] == "left" and t1["end_date"] == D[7]
assert t1["sessions_in_zone"] == 2 and t1["deepest_drawdown"] == -0.16
assert t1["ret_5"] == round(92 / 84 - 1, 6) and t1["ret_60"] is not None
near1 = eps[0]
assert near1["line"] == "near" and near1["end"] == "new_ath" and near1["end_date"] == D[10]
assert eps[-1]["end"] == "open" and eps[-1]["cycle_ath"] == 101.0
st = tl.stats(eps)
assert st["t1"]["entries"] == 1 and st["near"]["entries"] == 2 and st["t1"]["positive_5"] == "1/1"

# build: append-only, idempotent, historical replay apart, alert reconciliation
hist = bars_from([50, 60, 70, 80, 95, 78, 80, 96], start="2015-01-05")        # an old t1 episode (replay)
prices = {"VGT": hist + bars}
status = {"symbols": {"VGT": {"as_of": D[4], "drawdown": -0.16, "ath_implied": 100.0}},
          "events": [{"key": "VGT@100.0000|enter:t1", "symbol": "VGT", "kind": "enter", "line": "t1", "as_of": D[4],
                      "at": f"{D[5]}T02:00:00+00:00", "cycle_id": "VGT@100.0000", "drawdown": -0.16, "delivery": "sent"},
                     {"key": "VGT@104.0000|enter:t1", "symbol": "VGT", "kind": "enter", "line": "t1", "as_of": D[6],
                      "at": f"{D[7]}T16:00:00+00:00", "cycle_id": "VGT@104.0000", "drawdown": -0.19, "delivery": "sent"}]}
old_live, tl.LIVE_FROM = tl.LIVE_FROM, D[0]
try:
    rv, nd, ne = tl.build(prices, {"VGT": TIERS}, status, [], [], [], [], now=NOW, alerted=["VGT"])
    assert len(nd) == len(bars) and all(r["date"] >= tl.DAILY_FROM for r in nd)
    pub = next(r for r in nd if r["date"] == D[4])
    assert pub["published_drawdown"] == -0.16 and pub["published_mismatch"] is False
    tr = [r for r in ne if r["type"] == "transition"]
    assert {r["basis"] for r in tr} == {"historical_replay", "live_period"}, [(r["date"], r["basis"]) for r in tr]
    assert sum(1 for r in tr if r["basis"] == "historical_replay") == 2               # 2015: near + t1
    v = rv["symbols"]["VGT"]
    assert v["historical_replay"]["stats"]["t1"]["entries"] == 1 and v["historical_replay"]["to"] < "2016"
    assert v["live"]["counts"] == {"enter:near": 2, "enter:t1": 1, "leave:t1": 1}
    rec = rv["alert_reconciliation"]
    assert rec["matched"] == 1 and len(rec["unsupported_by_prices"]) == 1
    u = rec["unsupported_by_prices"][0]
    assert u["as_of"] == D[6] and u["alert_cycle_id"] == "VGT@104.0000" and u["price_ath"] == 100.0
    assert {(m["date"], m["transition"]) for m in rec["transitions_without_alert"]} == \
        {(D[3], "enter:near"), (D[7], "leave:t1"), (D[11], "enter:near")}
    assert rec["delay_hours_after_close"]["n"] == 2
    assert v["current"]["zone"] == "near" and v["current"]["next_line"] == "t1"

    # second run with the stored rows: nothing new
    rv2, nd2, ne2 = tl.build(prices, {"VGT": TIERS}, status, [], [], nd, ne, now=NOW, alerted=["VGT"])
    assert nd2 == [] and ne2 == [], (len(nd2), len(ne2))

    # a price revision appends a revision row; the stored row is untouched
    rev = [list(b) for b in prices["VGT"]]
    i = next(k for k, b in enumerate(rev) if b[0] == D[20])
    rev[i][3] = rev[i][3] * 1.01
    _, nd3, _ = tl.build({"VGT": [tuple(b) for b in rev]}, {"VGT": TIERS}, status, [], [], nd, ne, now=NOW, alerted=["VGT"])
    assert [r["type"] for r in nd3] == ["revision"] and nd3[0]["revises"]["close"] == 87.0

    # a published drawdown that disagrees with prices is flagged
    bad = {**status, "symbols": {"VGT": {"as_of": D[4], "drawdown": -0.19}}}
    rv4, nd4, _ = tl.build(prices, {"VGT": TIERS}, bad, [], [], [], [], now=NOW, alerted=["VGT"])
    assert rv4["published_mismatches"] == [{"symbol": "VGT", "date": D[4], "published": -0.19, "prices": -0.16}]
finally:
    tl.LIVE_FROM = old_live

# missing history -> explicit unavailable
rv5, _, _ = tl.build({}, {"QLD": {"t1": 0.25, "t2": 0.35, "t3": 0.5}}, {}, [], [], [], [], now=NOW)
assert rv5["symbols"]["QLD"] == {"status": "unavailable", "reason": "no_price_history"}

# shock thresholds after corrections; turning-point checklist counts
shocks = [{"type": "event", "event_id": "A@1", "subject": "A", "severity": "medium", "price_trigger": False, "news_trigger": True},
          {"type": "correction", "event_id": "A@1", "at": "x", "severity": "high", "price_trigger": True, "reason_zh": "r"},
          {"type": "event", "event_id": "B@1", "subject": "B", "severity": "medium", "price_trigger": True},
          {"type": "correction", "event_id": "B@1", "at": "y", "retracted": True, "reason_zh": "r"}]
sh = tl.shock_summary(shocks)
assert sh["events"] == 2 and sh["retracted"] == 1 and sh["by_severity"] == {"high": 1} and sh["price_triggers"] == 1
tp = tl.turning_summary([{"market_date": "2026-11-12", "met": 1, "statuses": {"s": "met"}, "trigger": False},
                         {"market_date": "2026-11-13", "met": 2, "statuses": {"s": "met", "e": "met"}, "trigger": False}])
assert tp["first_met"] == {"s": "2026-11-12", "e": "2026-11-13"} and tp["max_met"] == 2 and tp["trigger_sessions"] == 0

# file round trip is append-only
with tempfile.TemporaryDirectory() as t:
    p = Path(t) / "x.jsonl"
    tl.append_jsonl(p, [{"a": 1}])
    tl.append_jsonl(p, [{"a": 2}])
    assert [r["a"] for r in tl.read_jsonl(p)] == [1, 2]

src = (ROOT / "scripts" / "threshold_ledger.py").read_text(encoding="utf-8")
assert "urllib" not in src and "requests" not in src and "telegram" not in src.lower()
print("threshold ledger tests: OK")
