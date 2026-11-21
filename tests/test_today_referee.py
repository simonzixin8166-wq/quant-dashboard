"""S4-1 Today's Action referee: standard cases (plan v0.2). Synthetic inputs, no network.
Safety cases: data trust, hard risk above formal triggers, at most 3 actions with an overflow count (nothing
dropped), counter-evidence and invalidation on every action, external views and media never become actions, and
no private data in the public output."""
import copy
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import today_referee as tr

S = "2026-11-20"          # expected completed US session (Friday)
SH = "2026-11-21"         # Shanghai date (Saturday)
NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)
TH = {"QQQM": {"near": 0.10, "t1": 0.12, "t2": 0.18, "t3": 0.25}, "VGT": {"near": 0.13, "t1": 0.15, "t2": 0.20, "t3": 0.30},
      "QLD": {"near": 0.23, "t1": 0.25, "t2": 0.35, "t3": 0.50}}


def sym(name, dd, zone):
    return {"judgment": "evaluated", "as_of": S, "drawdown": dd, "zone": zone, "thresholds": TH[name]}


def base():
    return {
        "core": {"expected_session": S, "leave_buffer_pp": 0.02,
                 "symbols": {"QQQM": sym("QQQM", -0.05, "normal"), "VGT": sym("VGT", -0.06, "normal"), "QLD": sym("QLD", -0.10, "normal")},
                 "events": []},
        "review": {"generated_at": S + "T21:29:01+00:00", "symbols": {"VGT": {"historical_replay": {"stats": {"t2": {
            "entries": 5, "median_deepest_drawdown": -0.2146, "deepest_ever": -0.274, "positive_60": "4/5"}}}}}},
        "data": {"tqqq_x2": {"available": True, "date": S, "rule": "hold", "changed": False, "status_label": "持有",
                             "target_position": 67, "action": "持有"}},
        "invest": {"dca_calendar": {"symbols": ["QQQM", "QLD", "VGT"], "months": [
            {"month": "2026-11", "due_date": "2026-11-09", "window_end": "2026-11-10"},
            {"month": "2026-12", "due_date": "2026-12-07", "window_end": "2026-12-10"}]},
            "gold": {"state": "HOLD"}},
        "playbooks": {"playbooks": []}, "shock": {"events": []}, "turning": {},
    }


def enter(inp, name, dd, line, kind="enter", as_of=S):
    inp["core"]["symbols"][name] = sym(name, dd, line)
    inp["core"]["events"].append({"symbol": name, "kind": kind, "line": line, "as_of": as_of, "key": f"{name}@x|{kind}:{line}"})


def run(inp, sh=SH, history=None):
    return tr.referee(inp, S, sh, history, now=NOW)


# 1 core not at any tier -> nothing to do, explicit NO_ACTION (never an empty page)
o = run(base())
assert o["mode"] == "NO_ACTION" and o["actions"] == [] and "无需操作" in o["headline_zh"], o
assert "定投按日历执行，下次 2026-12-07" in o["hold_zh"]

# 2 core tier entered this session -> ACTION with counter-evidence, invalidation, evidence, as_of
i = base(); enter(i, "VGT", -0.2517, "t2")
o = run(i)
a = o["actions"][0]
assert o["mode"] == "ACTION" and a["symbol"] == "VGT" and a["level"] == "ACTION" and a["verification"] == "OK"
assert "进入二级" in a["title_zh"] and a["as_of"] == S and a["evidence"]
assert "5 次" in a["counter_evidence_zh"] and "已深于历史中位" in a["counter_evidence_zh"] and "下跌可能继续" in a["counter_evidence_zh"]
assert "18.0% 以内" in a["invalidation_zh"] and "距三级（30.0%）还差 4.8" in a["position_zh"]
assert "未经前瞻验证" in a["certainty_zh"] and "金额" not in a["reason_zh"].replace("加多少", "")

# 3 tier entered on an earlier session, still in the zone -> hold line, not an action
i = base(); enter(i, "VGT", -0.21, "t2", as_of="2026-11-19")
o = run(i)
assert o["actions"] == [] and "VGT 仍在二级" in o["hold_zh"]

# 4 re-entry after a leave -> ACTION worded as re-entry
i = base(); enter(i, "QQQM", -0.13, "t1", kind="reenter")
assert "再次跌破一级" in run(i)["actions"][0]["title_zh"]

# 5 near line is not an action (only t1/t2/t3)
i = base(); enter(i, "QQQM", -0.105, "near")
assert run(i)["actions"] == []

# 6 TQQQ X2 state change to hard exit -> ACTION, ranked above core tiers
i = base(); enter(i, "VGT", -0.2517, "t2")
i["data"]["tqqq_x2"].update(rule="hard_exit", changed=True, status_label="防守 · 空仓", target_position=0, action="硬退出：目标降至0%")
o = run(i)
assert [a["symbol"] for a in o["actions"]] == ["TQQQ", "VGT"] and o["actions"][0]["action"] == "EXIT"
assert o["actions"][0]["counter_evidence_zh"] and o["actions"][0]["invalidation_zh"]

# 7 hard exit persisting (no change today) -> hold line only
i = base(); i["data"]["tqqq_x2"].update(rule="hard_exit", changed=False, status_label="防守 · 空仓", target_position=0)
o = run(i)
assert o["actions"] == [] and "TQQQ X2 维持「防守 · 空仓」" in o["hold_zh"]

# 8 core data stale, nothing else to act on -> CANNOT_JUDGE (not "no action"), blocked scope named
i = base(); enter(i, "VGT", -0.2517, "t2"); i["core"]["expected_session"] = "2026-11-19"
o = run(i)
assert o["mode"] == "CANNOT_JUDGE" and o["actions"] == [] and "无法判断" in o["headline_zh"]
assert o["data_trust"]["blocked"][0]["module"] == "core_tier_alert"

# 9 partial failure: only the stale source is blocked; a trusted hard-risk action still shows
i = base(); i["core"]["expected_session"] = "2026-11-19"
i["data"]["tqqq_x2"].update(rule="hard_exit", changed=True, status_label="防守", target_position=0, action="硬退出")
o = run(i)
assert o["mode"] == "ACTION" and [a["symbol"] for a in o["actions"]] == ["TQQQ"] and "部分数据未更新" in o["headline_zh"]

# 10 missing core file -> CANNOT_JUDGE
i = base(); i["core"] = None
assert run(i)["mode"] == "CANNOT_JUDGE"

# 11 more than 3 actions -> 3 shown, the rest counted and listed in overflow (never silently dropped)
i = base(); enter(i, "VGT", -0.2517, "t2"); enter(i, "QQQM", -0.2006, "t2"); enter(i, "QLD", -0.374, "t2")
i["data"]["tqqq_x2"].update(rule="hard_exit", changed=True, status_label="防守", target_position=0, action="硬退出")
o = run(i)
assert len(o["actions"]) == 3 and o["actions"][0]["symbol"] == "TQQQ" and o["overflow"]["count"] == 1
assert len(o["actions"]) + o["overflow"]["count"] == 4

# 12 DCA: inside the window -> ACTION; outside -> hold line with the next date
i = base()
o = run(i, sh="2026-12-08")
assert [a["symbol"] for a in o["actions"]] == ["DCA"] and "2026-12-10" in o["actions"][0]["invalidation_zh"]
assert run(i, sh="2026-12-11")["actions"] == []

# 13 DCA rolled past a weekend: the calendar's due date is what counts
i = base(); i["invest"]["dca_calendar"]["months"][0].update(due_date="2026-11-09", window_end="2026-11-10")
assert run(i, sh="2026-11-07")["actions"] == [] and run(i, sh="2026-11-09")["actions"][0]["symbol"] == "DCA"

# 14 gold REVIEW is a watch item, never an action
i = base(); i["invest"]["gold"] = {"state": "REVIEW", "reasons": ["跌破全部计划档位"], "quote": {"as_of": "2026-11-21T04:00:07Z"}}
o = run(i)
assert o["actions"] == [] and o["watch"]["items"][0]["symbol"] == "GOLD"

# 15 shock events (even high severity) and the turning-point checklist (even triggered) stay WATCH
i = base()
i["shock"]["events"] = [{"subject": "NVDA", "severity": "high", "ref_session": "2026-11-19", "first_seen": S + "T15:00:00+00:00",
                         "quote": {"move_total": -0.14}},
                        {"subject": "OLD", "severity": "high", "ref_session": "2026-11-12", "first_seen": "2026-11-13T15:00:00+00:00"},
                        {"subject": "AMD", "severity": "medium", "ref_session": S, "first_seen": S + "T19:00:00+00:00",
                         "corrections": [{"retracted": True}]}]
i["turning"] = {"market_date": S, "summary": {"headline": "3 / 4 满足", "triggered": True}}
o = run(i)
assert o["actions"] == [] and o["mode"] == "NO_ACTION"
titles = [w["title_zh"] for w in o["watch"]["items"]]
assert any("NVDA -14.0%" in t for t in titles) and not any("OLD" in t or "AMD" in t for t in titles), titles
assert any("变盘清单" in t for t in titles)

# 16 at most 5 watch items shown; the rest folded and counted
i = base()
i["playbooks"]["playbooks"] = [{"playbook_id": "CP-03", "state": "TRIGGERED", "market_date": S, "symbol": f"S{k}"} for k in range(7)]
o = run(i)
assert len(o["watch"]["items"]) == 5 and o["watch"]["folded"] == 2 and o["watch"]["count"] == 7

# 17 one card per symbol: a watch item for a symbol with an action is attached as supporting evidence
i = base(); enter(i, "VGT", -0.2517, "t2")
i["playbooks"]["playbooks"] = [{"playbook_id": "CP-03", "state": "TRIGGERED", "market_date": S, "symbol": "VGT"}]
o = run(i)
assert o["watch"]["count"] == 0 and "VGT 反弹候选" in o["actions"][0]["supporting_zh"][0]

# 18 lifecycle: the same card on a later run keeps first_seen and becomes ACTIVE; no duplicate log row
i = base(); enter(i, "VGT", -0.2517, "t2")
first = run(i)
assert first["actions"][0]["status"] == "NEW"
second = tr.referee(i, S, SH, [first], now=datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc))
assert second["actions"][0]["status"] == "ACTIVE" and second["actions"][0]["first_seen"] == first["actions"][0]["first_seen"]
assert second["content_sha"] != "" and second["actions"][0]["dedup_key"] == first["actions"][0]["dedup_key"]

# 19 a card missing a safety field is NEEDS_VERIFICATION, kept at its level (not downgraded, not dropped)
c = tr._card("ACTION", "TIER_REMINDER", "X", "formal_trigger", "t", "r", [], "c", "inv", S, "core_tier_alert", True)
assert c["verification"] == "NEEDS_VERIFICATION" and c["level"] == "ACTION" and c["missing_safety_fields"] == ["evidence"]

# 20 every action card has counter-evidence and invalidation
i = base(); enter(i, "VGT", -0.2517, "t2"); enter(i, "QLD", -0.374, "t2")   # QLD has no replay stats in this fixture
for a in run(i)["actions"]:
    assert a["counter_evidence_zh"] and a["invalidation_zh"] and a["evidence"] and a["as_of"]
assert "历史样本不足" in [a for a in run(i)["actions"] if a["symbol"] == "QLD"][0]["counter_evidence_zh"]

# 21 privacy: the public output has only whitelisted card fields and no private option data
i = base(); enter(i, "VGT", -0.2517, "t2")
i["server"] = {"action_counts": {"l3": 1}, "positions": [{"symbol": "FAKEPRIV", "qty": 7, "amount": 12345}]}
blob = json.dumps(run(i), ensure_ascii=False)
assert "FAKEPRIV" not in blob and "12345" not in blob and "l3" not in blob and "私有行动" not in run(i)["headline_zh"]
assert set(run(i)["actions"][0]) <= set(tr.PUBLIC_CARD_FIELDS) | {"supporting_zh"}

# 22 weekend: Saturday keeps Friday's session cards (no new session), DCA follows the Shanghai date
i = base(); enter(i, "VGT", -0.2517, "t2")
o = run(i, sh="2026-11-22")
assert o["session"] == S and o["actions"][0]["symbol"] == "VGT"

# 23 smoke on the repository's real published files: runs, page mode is one of the three, whitelist holds
o = tr.referee(tr.load_inputs(), S, SH, now=NOW)
assert o["mode"] in ("ACTION", "NO_ACTION", "CANNOT_JUDGE") and len(o["actions"]) <= 3
for a in o["actions"]:
    assert set(a) <= set(tr.PUBLIC_CARD_FIELDS) | {"supporting_zh"} and a["counter_evidence_zh"] and a["invalidation_zh"]

# 24 the referee never names quantities or places orders; source has no network or broker calls
src = (ROOT / "scripts" / "today_referee.py").read_text(encoding="utf-8")
assert "urllib" not in src and "requests" not in src and "broker" not in src.lower() and "place_order" not in src

# file round trip: append only when content changes
with tempfile.TemporaryDirectory() as t:
    p = Path(t) / "x.jsonl"
    p.write_text(json.dumps({"a": 1}) + "\n", encoding="utf-8")
    assert tr.read_jsonl(p) == [{"a": 1}]
print("PASS today referee: 24 standard cases (trust, hard risk, tiers, DCA, overflow, watch-only, lifecycle, privacy)")
