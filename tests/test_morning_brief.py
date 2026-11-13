"""Morning brief: honest about late data, Owner's tiers, shock events (retracted skipped), calendar in Shanghai
time, one send per day plus one update when the close arrives late. Synthetic inputs, no network."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import morning_brief as mb

tiers = json.loads((ROOT / "config" / "playbooks.public.json").read_text(encoding="utf-8"))["core_tiers"]
NOW = datetime(2026, 11, 13, 0, 37, tzinfo=timezone.utc)          # Fri 08:37 Shanghai; expected session 11/12


def row(d, close, dd, chg=0.01):
    return {"date": d, "close": close, "strategy_drawdown": dd, "ath_is_true": True, "ath_validation": "PASS", "day_chg": chg}


def data(d):
    return {"stocks": {"NVDA": row(d, 166.19, -0.3, -0.0434)}, "index": {"QQQ": row(d, 680, -0.108, -0.015), "SMH": row(d, 490, -0.27, -0.03)},
            "market_indicators": {"ixic": row(d, 25000, -0.1, -0.012), "spx": row(d, 7550, -0.03, -0.006),
                                  "vix": {"date": d, "close": 20.4, "day_chg": 0.11}},
            "core": {"QQQM": row(d, 280.1, -0.1083), "VGT": row(d, 111.0, -0.152), "QLD": row(d, 79.0, -0.2226)}}


shock = {"events": [
    {"event_id": "NVDA@x", "subject": "NVDA", "kind": "company", "severity": "high", "first_seen": "2026-11-12T13:05:13+00:00",
     "quote": {"move_total": -0.0743}, "advice": ["核心…", "NVDA：管理层或治理事件，结果未定。", "期权：…", "研究提示…"],
     "upcoming": [{"date": "2026-11-17", "title_zh": "NVDA 财报"}]},
    {"event_id": "AMD@x", "subject": "AMD", "kind": "company", "severity": "medium", "first_seen": "2026-11-12T13:05:13+00:00",
     "quote": {"move_total": 0.0544}, "advice": ["核心…", "AMD：原因未经核实前…", "同期 NVDA 也有事件，两者可能相关（未核实）。"]},
    {"event_id": "X@x", "subject": "X", "kind": "company", "severity": "medium", "retracted": True,
     "first_seen": "2026-11-12T13:05:13+00:00", "quote": {"move_total": 0.09}, "advice": []},
    {"event_id": "OLD@x", "subject": "OLD", "kind": "company", "severity": "high", "first_seen": "2026-11-01T13:05:13+00:00",
     "quote": {"move_total": 0.09}, "advice": []}]}
calendar = {"events": [{"date": "2026-11-13", "title_zh": "美国 PPI", "datetime": "2026-11-13T08:30:00-05:00"},
                       {"date": "2026-11-17", "title_zh": "NVDA 财报", "time_status": "unofficial_date"},
                       {"date": "2026-11-30", "title_zh": "远期", "datetime": None}]}
learn = {"learning_state": "UNPROVEN", "measures": {
    "understanding": {"production": {"recall": {"k": 27, "n": 70}}, "rows": [{"extractor": "gemini-claims-0.2", "status": "partial", "answered_posts": 51}]},
    "judgments": {"observations": 672}, "experience": {"h20": {"scored": 110, "hits": 77}}}}
status = {"overall": "running", "active_module_failures": {}}
common = dict(tiers=tiers, shock=shock, calendar=calendar, learn=learn, status=status)

b = mb.build(now=NOW, data=data("2026-11-12"), **common)
t = b["text"]
assert b["fresh"] and "尚未更新" not in t and "MyAlpha 早报 · 11/13 五" in t
assert "QQQM 回撤 10.8%（已到接近一级线，距一级 1.2%）" in t and "VGT 回撤 15.2%（已到一级线，距二级 4.8%）" in t
assert "QLD 回撤 22.3%（正常区，距一级 2.7%）" in t
lines = t.splitlines()
i = lines.index("突发事件：")
assert lines[i + 1].startswith("· [高] NVDA 11/12 收盘 -4.3%（发现时 -7.4%）：管理层/治理事件") and "11/17 NVDA 财报" in lines[i + 1]
assert "AMD +5.4%：同行联动，可能与 NVDA 事件相关" in t and " X " not in t and "OLD" not in t
assert "今天 美国 PPI（北京 11/13 21:30）" in t and "11/17" not in t.split("日程")[1].split("\n")[0]
assert "Gemini 进行中 51/85" in t and "生产召回率 27/70" in t and "系统：正常" in t and t.endswith(mb.DISCLAIMER)
print("PASS content: tiers, shock events (high first, retracted/old skipped), Shanghai times, learning, health")

stale = mb.build(now=NOW, data=data("2026-11-11"), **common)
assert not stale["fresh"] and "⚠ 美股 2026-11-12 收盘数据尚未更新（最新 2026-11-11）" in stale["text"] and "数据未到" in stale["text"]
assert "NVDA 11/11 收盘" not in stale["text"] and "NVDA -7.4%" in stale["text"], "a close before the event is not shown"
print("PASS late close is said plainly, never filled in")

d = Path(tempfile.mkdtemp())
sent = []
kw = dict(state_path=d / "s.json", out_path=d / "o.json", send=lambda x: sent.append(x) or "sent", **common)
mb.run(now=NOW, data=data("2026-11-11"), **kw)
mb.run(now=NOW.replace(hour=1), data=data("2026-11-11"), **kw)
assert len(sent) == 1
mb.run(now=NOW.replace(hour=2), data=data("2026-11-12"), **kw)
assert len(sent) == 2 and sent[1].startswith("MyAlpha 早报（收盘数据已更新）")
mb.run(now=NOW.replace(hour=3), data=data("2026-11-12"), **kw)
assert len(sent) == 2
print("PASS one brief per day; one update when the close arrives late")

wf = (ROOT / ".github/workflows/morning-brief.yml").read_text(encoding="utf-8")
assert "privacy_canary_scan.py --staged" in wf and "37 0 * * *" in wf
print("PASS workflow wiring")
