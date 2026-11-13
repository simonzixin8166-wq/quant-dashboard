"""Shock-event monitor: detection, append-only ledger, merging, advice, core impact against the Owner's tiers,
follow-ups, one Telegram message per event. Synthetic quotes and headlines only (no network)."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import shock_event_monitor as sm

cfg = json.loads((ROOT / "config" / "shock_watch.json").read_text(encoding="utf-8"))
tiers = json.loads((ROOT / "config" / "playbooks.public.json").read_text(encoding="utf-8"))["core_tiers"]
REG_START = int(datetime(2026, 11, 12, 14, 30, tzinfo=timezone.utc).timestamp())
REG_END = int(datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc).timestamp())


def chart(prev, pts, rmp=None):
    return {"chart": {"result": [{"meta": {"chartPreviousClose": prev, "regularMarketPrice": rmp or pts[-1][1],
                                           "currentTradingPeriod": {"regular": {"start": REG_START, "end": REG_END}}},
                                  "timestamp": [t for t, _ in pts],
                                  "indicators": {"quote": [{"close": [c for _, c in pts]}]}}]}}


PRE = int(datetime(2026, 11, 12, 12, 40, tzinfo=timezone.utc).timestamp())
POST = int(datetime(2026, 11, 12, 21, 20, tzinfo=timezone.utc).timestamp())

# parse: premarket move from the previous close; after-hours move anchored to today's close
q = sm.parse_chart(chart(173.73, [(PRE - 600, None), (PRE, 160.0)]), "NVDA")
assert q["session"] == "pre" and q["ref_session"] == "2026-11-11" and q["move_total"] == round(160 / 173.73 - 1, 4)
q2 = sm.parse_chart(chart(170.0, [(REG_END - 60, 173.0), (POST, 158.0)], rmp=173.0), "NVDA")
assert q2["session"] == "post" and q2["ref_session"] == "2026-11-12" and q2["ref_price"] == 173.0
assert q2["move_ext"] == round(158 / 173 - 1, 4)
assert sm.parse_chart({"chart": {"result": []}}, "X")["status"] == "unavailable"
print("PASS chart parsing: pre/post sessions, reference close, unavailable on bad payload")

NOW = datetime(2026, 11, 12, 12, 45, tzinfo=timezone.utc)
moves = {"NVDA": 160.0 / 173.73, "QQQ": 0.992, "SPY": 0.996, "VGT": 0.985, "SMH": 0.985, "QQQM": 0.992, "QLD": 0.984}


BASE = {"QQQM": 284.23, "VGT": 113.72, "QLD": 81.83}


def quote(sym):
    if sym == "^VIX":
        return {"symbol": sym, "status": "ok", "last": 19.0, "move_total": 0.06, "move_ext": 0.06, "session": "pre",
                "ref_session": "2026-11-11", "last_time": "2026-11-12T12:40:00+00:00"}
    if sym == "AMD":
        return {"symbol": sym, "status": "unavailable", "reason": "HTTPError"}
    m = moves.get(sym, 1.0)
    base = BASE.get(sym, 100.0)
    return {"symbol": sym, "status": "ok", "prev_close": base, "ref_price": base, "last": round(base * m, 4),
            "move_total": round(m - 1, 4), "move_ext": round(m - 1, 4), "move_day": None, "session": "pre",
            "ref_session": "2026-11-11", "last_time": "2026-11-12T12:40:00+00:00"}


def news(sym):
    if sym != "NVDA":
        return {"status": "ok", "items": [{"title": f"{sym} shares edge higher", "publisher": "A",
                                           "published_at": "2026-11-12T10:00:00+00:00", "url": "u"}]}
    pubs = ["CNBC", "Bloomberg", "Reuters", "CNBC"]
    items = [{"title": f"Nvidia board weighs ousting CEO Jensen Huang ({i})", "publisher": p,
              "published_at": f"2026-11-12T0{i}:00:00+00:00", "url": f"https://x/{i}"} for i, p in enumerate(pubs)]
    items.append({"title": "Nvidia CEO probe: old story", "publisher": "Old", "published_at": "2026-11-09T00:00:00+00:00", "url": "o"})
    return {"status": "ok", "items": items}


data = {"core": {
    "QQQM": {"close": 284.23, "strategy_drawdown": -0.09514, "ath_is_true": True, "ath_validation": "PASS", "date": "2026-11-11"},
    "VGT": {"close": 113.72, "strategy_drawdown": -0.12965, "ath_is_true": True, "ath_validation": "PASS", "date": "2026-11-11"},
    "QLD": {"close": 81.83, "strategy_drawdown": -0.19475, "ath_is_true": True, "ath_validation": "PASS", "date": "2026-11-11"}}}
calendar = {"events": [{"symbol": "NVDA", "date": "2026-11-17", "title_zh": "NVDA 财报", "time_status": "unofficial_date"}]}
sent = []
d = Path(tempfile.mkdtemp())
paths = dict(ledger_path=d / "l.jsonl", state_path=d / "s.json", out_path=d / "o.json")


def run(now, send_result="sent", **kw):
    return sm.run(now=now, quote=kw.get("quote", quote), news=kw.get("news", news), daily=kw.get("daily", lambda s: {}),
                  send=lambda t: sent.append(t) or send_result, cfg=cfg, data=data, tiers=tiers, calendar=calendar,
                  pause=0, **paths)


r = run(NOW)
assert r["new_events"] == ["NVDA@2026-11-11"], r["new_events"]
e = r["events"][0]
assert e["severity"] == "high" and e["price_trigger"] and e["news_trigger"] and e["facts_status"] == "reported_unverified"
assert len(e["headlines"]) == 4 and all("Old" != h["publisher"] for h in e["headlines"]), "stale headline excluded"
assert e["upcoming"][0]["date"] == "2026-11-17" and e["production_use"] is False and e["delivery"] == "sent"
assert "AMD" in r["checked"]["unavailable"]
print("PASS detection: price + headline cluster from 3+ publishers -> one high event; stale news ignored")

imp = {x["symbol"]: x for x in e["core_impact"]}
assert imp["QQQM"]["price_source"] == "QQQM" and imp["VGT"]["next_line"] == "t1" and imp["VGT"]["reached"] == "near"
assert abs(imp["VGT"]["est_drawdown"] - (113.72 * 0.985 / (113.72 / (1 - 0.12965)) - 1)) < 1e-4
adv = " ".join(e["advice"])
assert "VGT" in adv and "接近一级" in adv and "董事会正式公告" in adv and "2026-11-17" in adv and "期权" in adv
assert e["advice"][-1] == sm.DISCLAIMER
print("PASS analysis: core drawdown vs the Owner's tiers, governance advice, earnings ahead, disclaimer")

assert len(sent) == 1 and "突发事件：NVDA" in sent[0] and "未经核实" in sent[0] and "-7.9%" in sent[0]
print("PASS Telegram text")

# second run (after the close) joins the open event: observation only, no second message
r2 = run(datetime(2026, 11, 12, 21, 20, tzinfo=timezone.utc))
assert r2["new_events"] == [] and r2["updated_events"] == ["NVDA@2026-11-11"] and len(sent) == 1
rows = sm.read_ledger(paths["ledger_path"])
assert [x["type"] for x in rows].count("event") == 1 and [x["type"] for x in rows].count("observation") == 2
print("PASS open event merges; append-only ledger grows by observations; one message per event")

# follow-ups after 1 and 5 sessions; append once
closes = {"NVDA": {"2026-11-11": 173.73, "2026-11-12": 160.0, "2026-11-18": 150.0},
          "QQQ": {"2026-11-11": 690.38, "2026-11-12": 684.0, "2026-11-18": 700.0}}
r3 = run(datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc), daily=lambda s: closes.get(s, {}))
outs = {o["n"]: o for o in r3["events"][0]["outcomes"]}
assert set(outs) == {1, 5} and outs[1]["NVDA"] == round(160 / 173.73 - 1, 4) and outs[5]["QQQ"] == round(700 / 690.38 - 1, 4)
run(datetime(2026, 11, 19, 2, 0, tzinfo=timezone.utc), daily=lambda s: closes.get(s, {}))
assert len([x for x in sm.read_ledger(paths["ledger_path"]) if x["type"] == "outcome"]) == 2
print("PASS follow-ups after 1/5 sessions, appended once")

# quiet day: nothing found, nothing sent; failed delivery retried at most 3 times
sent.clear()
d2 = Path(tempfile.mkdtemp())
paths.update(ledger_path=d2 / "l.jsonl", state_path=d2 / "s.json", out_path=d2 / "o.json")
moves.update(NVDA=1.01, QQQ=1.001, SPY=1.0, VGT=1.0, SMH=1.0)
quiet = run(NOW, news=lambda s: {"status": "ok", "items": []})
assert quiet["new_events"] == [] and not sent and not paths["ledger_path"].exists()
moves.update(QQQ=0.97)
for i in range(4):
    run(datetime(2026, 11, 12, 13 + i, 0, tzinfo=timezone.utc), send_result="failed:URLError",
        news=lambda s: {"status": "ok", "items": []})
st = json.loads(paths["state_path"].read_text())
assert len(sent) == 3 and st["MARKET@2026-11-11"]["status"] == "failed" and st["MARKET@2026-11-11"]["attempts"] == 3
print("PASS quiet day writes nothing; market event; failed delivery retried at most 3 times")

# keyword matching uses word boundaries for English ("ban" does not match "bank")
assert sm._kw_hit("Nvidia bank partner", ["ban"]) is None and sm._kw_hit("board weighs ousting CEO", ["oust"]) == "oust" and sm._kw_hit("US export ban hits Nvidia", ["export ban"])
print("PASS keyword boundaries")

# --- production bug 2026-11-12: before the open the 1d chart spans the previous session, so chartPreviousClose is
# the close two sessions back (NVDA 168.80 = 11/10) while regularMarketPrice is the last close (173.73 = 11/11).
Y_START = int(datetime(2026, 11, 11, 14, 30, tzinfo=timezone.utc).timestamp())
pm = {"chart": {"result": [{"meta": {"chartPreviousClose": 168.796, "regularMarketPrice": 173.73,
                                     "regularMarketTime": Y_START + 6 * 3600 + 1800,
                                     "currentTradingPeriod": {"regular": {"start": REG_START, "end": REG_END}}},
                            "timestamp": [Y_START, Y_START + 23000, PRE],
                            "indicators": {"quote": [{"close": [170.0, 173.7, 160.82]}]}}]}}
qp = sm.parse_chart(pm, "NVDA")
assert qp["session"] == "pre" and qp["prev_close"] == 173.73 and qp["move_total"] == round(160.82 / 173.73 - 1, 4), qp
print("PASS premarket reference is the last regular close, not chartPreviousClose (11/12 bug)")

# anchor: the Daily close of the reference session wins over chart metadata; a different date is left alone
raw = {"symbol": "QQQM", "status": "ok", "last": 281.2, "move_total": 0.012, "move_ext": 0.012, "session": "pre",
       "ref_session": "2026-11-11"}
a = sm.anchor(raw, data)
assert a["anchor"] == "daily_close" and a["ref_price"] == 284.23 and a["move_total"] == round(281.2 / 284.23 - 1, 4)
assert sm.anchor(dict(raw, ref_session="2026-11-10"), data)["move_total"] == 0.012
print("PASS anchor to the Daily close of the reference session")

# a peer's headline (AMD up on Nvidia news) is not a governance event for the peer
ev_amd = {"subject": "AMD", "kind": "company", "news_trigger": False,
          "news": {"items": [{"title": "AMD, Broadcom gain after reports say Nvidia board preparing to oust Huang"}]}}
tips = " ".join(sm.advice(ev_amd, [], [], others=["NVDA"]))
assert "管理层或治理事件" not in tips and "NVDA" in tips and "可能相关" in tips
print("PASS peer headline gives no governance advice; links to the concurrent event")

# corrections are append-only rows; the public view applies them and hides retracted events
e0 = {"event_id": "AMD@x", "quote": {"move_total": 0.085}, "advice": ["old"]}
c = [{"type": "correction", "event_id": "AMD@x", "at": "t", "retracted": True, "reason_zh": "参考收盘价取错",
      "quote": {"move_total": 0.011}}]
v = sm.apply_corrections(e0, c)
assert v["retracted"] and v["quote"]["move_total"] == 0.011 and v["advice"] == ["old"] and e0["quote"]["move_total"] == 0.085
assert v["corrections"][0]["reason_zh"] == "参考收盘价取错"
js = (ROOT / "docs/assets/shock-event-row.js").read_text(encoding="utf-8")
assert "!e.retracted" in js and "更正" in js
print("PASS corrections applied in the public view; retracted events hidden on the homepage")

# a headline naming several watched companies is a peer reaction, not the cluster of any one of them
peer = [{"title": "AMD, Broadcom gain after reports say Nvidia board preparing to oust Huang", "publisher": p,
         "published_at": "2026-11-12T10:00:00+00:00"} for p in ("A", "B", "C")]
assert not sm.news_cluster("AVGO", cfg["stocks"]["AVGO"], peer, cfg, NOW)["hit"]
assert not sm.news_cluster("NVDA", cfg["stocks"]["NVDA"], peer, cfg, NOW)["hit"]
print("PASS peer headlines naming several companies never trigger a cluster (AVGO 11/12)")
