"""Core-ETF tier alerts (Owner #133 6516033003 / 6537316711): once per line per drawdown cycle, near = 2 pp,
recovery out of a tier alerts once, cannot-judge never fires a trigger, no positions/amounts in output."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import core_tier_state as cts
import core_tier_alert as cta

T = {"t1": 0.12, "t2": 0.18, "t3": 0.25}
# zones and thresholds come from config tiers; near = t1 - 2 pp
assert cts.thresholds(T)["near"] == 0.10
assert [cts.zone(x, T) for x in (0.05, 0.10, 0.12, 0.19, 0.30)] == ["normal", "near", "t1", "t2", "t3"]

# a path inside one cycle: near -> t1 -> wobble at the line (no repeats) -> t2 -> recover -> recover -> dip again
st, seen = {}, []
for loss in (0.06, 0.101, 0.121, 0.118, 0.123, 0.119, 0.185, 0.17, 0.155, 0.09, 0.125):
    st, ev = cts.advance(st, loss, 100.0, T)
    seen += ev
assert seen == [("enter", "near"), ("enter", "t1"), ("enter", "t2"), ("leave", "t2"), ("leave", "t1")], seen
# a new all-time high re-arms every line
st, ev = cts.advance(st, 0.0, 101.0, T)
assert ev == [] and st["sent"] == []
st, ev = cts.advance(st, 0.13, 101.0, T)
assert ev == [("enter", "near"), ("enter", "t1")]
# a gap straight into t3 reports every line crossed, deepest last
st, ev = cts.advance({}, 0.30, 100.0, T)
assert [e[1] for e in ev] == ["near", "t1", "t2", "t3"]

# build(): only CP-01 assets, uses config tiers, one message per event, nothing repeated on a rerun
config = json.loads((ROOT / "config" / "playbooks.public.json").read_text())
assets = next(p["assets"] for p in config["playbooks"] if p["playbook_id"] == "CP-01")
def core(dd_qqqm, valid="PASS"):
    return {"core": {s: {"date": "2026-11-02", "close": 100.0, "strategy_drawdown": -0.05, "ath_is_true": True,
                         "ath_validation": "PASS"} for s in assets} | {"QQQM": {"date": "2026-11-02", "close": 100.0,
                         "strategy_drawdown": dd_qqqm, "ath_is_true": True, "ath_validation": valid}}}
ok = {"data_trust": {"ok": True, "market_as_of": "2026-11-02", "expected_market_date": "2026-11-02"}}
# 2026-11-03 00:30Z = 11/02 19:30 ET, after the close -> expected session 2026-11-02
msgs = []
send = lambda t: msgs.append(t) or "sent"
now = datetime(2026, 11, 3, 0, 30, tzinfo=timezone.utc)
o1 = cta.build(now, send, core(-0.125), config, ok, {})
assert set(o1["symbols"]) == set(assets) and "QQQ" not in o1["symbols"]
assert len(msgs) == 2 and "接近一级" in msgs[0] and "进入一级加仓线" in msgs[1], msgs
assert "12.5%" in msgs[1] and "数据日期 2026-11-02" in msgs[1] and cta.DISCLAIMER in msgs[1]
assert all(e["delivery"] == "sent" for e in o1["events"])
o2 = cta.build(now, send, core(-0.124), config, ok, o1)
assert len(msgs) == 2 and o2["symbols"]["QQQM"]["zone"] == "t1"          # same state: no repeat
o3 = cta.build(now, send, core(-0.09), config, ok, o2)
assert len(msgs) == 3 and "回升，已离开一级" in msgs[2]                     # recovered by >= 2 pp below the line
# cannot judge: untrusted data or unvalidated ATH -> one 'cannot judge', no trigger, state kept
bad = {"data_trust": {"ok": False, "market_as_of": "2026-11-02", "expected_market_date": "2026-11-02"}}
o4 = cta.build(now, send, core(-0.20), config, bad, o3)
assert len(msgs) == 3 + len(assets) and all("暂不能判断" in m for m in msgs[3:]), msgs[3:]
assert o4["symbols"]["QQQM"]["sent"] == o3["symbols"]["QQQM"]["sent"]       # nothing advanced
o5 = cta.build(now, send, core(-0.20), config, bad, o4)
assert len(msgs) == 3 + len(assets)                                         # cannot-judge also not repeated
o6 = cta.build(now, send, core(-0.20, valid="CHECK"), config, ok, {})
assert all("暂不能判断" in m for m in msgs[3 + len(assets):]) and o6["symbols"]["QQQM"]["judgment"] == "cannot_judge"
# stale rows (yesterday's data on today's run) are never judged
late = datetime(2026, 11, 4, 0, 30, tzinfo=timezone.utc)
o8 = cta.build(late, lambda t: "sent", core(-0.13), config, ok, {})
assert o8["symbols"]["QQQM"]["judgment"] == "cannot_judge" and o8["symbols"]["QQQM"]["reason"].startswith("stale_data")
# a failed Telegram delivery is recorded, never raised
o7 = cta.build(now, lambda t: "failed:URLError", core(-0.13), config, ok, {})
assert o7["events"][-1]["delivery"] == "failed:URLError"
# public output: no positions or amounts
blob = json.dumps([o1, o3, o4, o7], ensure_ascii=False)
for word in ("position", "shares", "cost", "amount", "持仓", "金额"):
    assert word not in blob, word

# homepage banner: hidden when every CP-01 asset is normal; red for a tier, amber for near; escapes; disclaimer
import fetch_and_build as fb
assert fb.core_tier_banner_html(core(-0.05)["core"]) == ""
b1 = fb.core_tier_banner_html(core(-0.105)["core"])
assert 'data-core-tier-banner="near"' in b1 and "接近一级" in b1 and "#f9eeda" in b1 and cta.DISCLAIMER in b1
b2 = fb.core_tier_banner_html(core(-0.13)["core"])
assert 'data-core-tier-banner="t1"' in b2 and "已进入一级加仓线" in b2 and "#fbebeb" in b2
assert fb.core_tier_banner_html(core(-0.13, valid="CHECK")["core"]) == ""        # unvalidated ATH: no banner
src = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")
assert src.count("{core_tier_banner_html(data.get('core'))}") == 1

# --- GPT 6537701769 §1/§2 rigor ---------------------------------------------------------------
# leaving a line never re-arms its 'enter' alert within the cycle (second dip in the same cycle: page only)
st, ev1 = cts.advance({}, 0.13, 100.0, T)
st, ev2 = cts.advance(st, 0.09, 100.0, T)
st, ev3 = cts.advance(st, 0.14, 100.0, T)
assert ("leave", "t1") in ev2 and ev3 == [] and st["zone"] == "t1"
# new cycle only on a plausible validated new ATH; a jump (split / adjustment artefact) is 'suspect'
assert cts.new_cycle_check(100.0, 100.005) == "same" and cts.new_cycle_check(100.0, 103.0) == "new"
assert cts.new_cycle_check(100.0, 200.0) == "suspect" and cts.new_cycle_check(None, 50.0) == "new"
# row checks: close must be finite/positive, drawdown in range, no unexplained day jump
base = {"date": "2026-11-02", "close": 100.0, "prev_close": 99.0, "strategy_drawdown": -0.05, "ath_is_true": True, "ath_validation": "PASS"}
assert cts.row_inputs(base, T)[2] == "ok"
assert cts.row_inputs({**base, "close": 0}, T)[2] == "close_invalid"
assert cts.row_inputs({**base, "close": float("nan")}, T)[2] == "close_invalid"
assert cts.row_inputs({**base, "strategy_drawdown": 0.3}, T)[2] == "drawdown_out_of_range"
assert cts.row_inputs({**base, "prev_close": 50.0}, T)[2] == "price_jump_unexplained"
# suspect ATH in build(): cannot judge, cycle kept, no trigger
prev = cta.build(now, lambda t: "sent", core(-0.13), config, ok, {})
jump = core(-0.13); jump["core"]["QQQM"]["close"] = 300.0          # implied ATH ~345 vs cycle ~115
o9 = cta.build(now, lambda t: "sent", jump, config, ok, prev)
assert o9["symbols"]["QQQM"]["judgment"] == "cannot_judge" and o9["symbols"]["QQQM"]["reason"] == "ath_jump_unverified"
assert o9["symbols"]["QQQM"]["cycle_ath"] == prev["symbols"]["QQQM"]["cycle_ath"]
# Telegram: failed sends are retried on later runs (max 3 attempts), each alert key is sent at most once
calls = []
def flaky(t):
    calls.append(t); return "failed:URLError" if len(calls) <= 2 else "sent"
r1 = cta.build(now, flaky, core(-0.13), config, ok, {})           # near + t1 queued, both fail (2 calls)
assert len(calls) == 2 and all(o["status"] == "failed" for o in r1["outbox"])
r2 = cta.build(now, flaky, core(-0.13), config, ok, r1)           # retries: near -> sent, t1 -> sent
assert len(calls) == 4 and all(o["status"] == "sent" for o in r2["outbox"]) and all(o["attempts"] == 2 for o in r2["outbox"])
r3 = cta.build(now, flaky, core(-0.13), config, ok, r2)           # nothing re-sent
assert len(calls) == 4
dead = cta.build(now, lambda t: "failed:X", core(-0.13), config, ok, {})
for _ in range(5):
    dead = cta.build(now, lambda t: "failed:X", core(-0.13), config, ok, dead)
assert all(o["attempts"] == cta.MAX_SEND_ATTEMPTS for o in dead["outbox"])
assert len({o["key"] for o in r2["outbox"]}) == len(r2["outbox"])
# audit fields recorded for every asset
assert all(k in r2["symbols"]["QQQM"] for k in ("as_of", "expected_session", "ath_implied", "ath_validation", "cycle_id"))

# 10-year replay sanity on the committed STOOQ history (QQQ tiers): 7 / 4 / 2 tier entries since 2016-10-31
import csv, io, zipfile
z = zipfile.ZipFile(ROOT / "data" / "history" / "stooq_watchlist.zip")
rows = list(csv.DictReader(io.TextIOWrapper(z.open("qqq_us_d.csv"), encoding="utf-8")))
st, peak, cnt = {}, 0.0, {}
for r in rows:
    if r["Date"] > "2026-10-30":
        break
    peak = max(peak, float(r["High"]))
    st, ev = cts.advance(st, 1 - float(r["Close"]) / peak, peak, T)
    if r["Date"] >= "2016-10-31":
        for k, line in ev:
            cnt[(k, line)] = cnt.get((k, line), 0) + 1
assert (cnt.get(("enter", "t1")), cnt.get(("enter", "t2")), cnt.get(("enter", "t3"))) == (7, 4, 2), cnt
assert sum(cnt.values()) <= 40, cnt   # about 4 alerts a year, not daily noise
print("PASS core tier alerts: near 2pp, suspect ATH, row checks, idempotent outbox + retry, once per line per cycle, recovery alert, cannot-judge, no amounts, 10y replay 7/4/2")
