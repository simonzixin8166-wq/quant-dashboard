#!/usr/bin/env python3
"""R-02 / H-01..H-02 — homepage macro-event reminder artifact (#133 6138793593). Read-only Shadow.

Builds docs/research/macro_event_watch.json from
  research/macro_events/event_facts_2026q4.json   official calendar (+ official outcomes once released)
  scripts/brightline_tranche_shadow.py            three-tranche state evaluated on the current inputs
  docs/data.json / macro_context / breadth        as_of of every input
Phase boundaries are precomputed in UTC with DST-aware America/New_York dates so the page can show
"事件前 / 已发布 / T+n" from the clock alone — a pre-event reminder never waits for a post-close run.
Nothing here is an order: production_use=false, used_in_decision=false; no BUY/SELL wording.
"""
from __future__ import annotations
import json, sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402
import brightline_tranche_shadow as bl  # noqa: E402

ET = ZoneInfo("America/New_York")
OUT = ROOT / "docs" / "research" / "macro_event_watch.json"
ANALYSIS_URL = "https://github.com/simonzixin8166-wq/quant-dashboard/blob/main/research/shadow_theses/brightline_8524_analysis_zh.md"
ARTICLE_URL = "https://blog.wenxuecity.com/myblog/82458/202610/8524.html"
CLOSE = time(16, 15)  # conservative close-confirmation buffer used across MyAlpha


def et_utc(d, t=time(0, 0)):
    return datetime.combine(date.fromisoformat(d) if isinstance(d, str) else d, t, ET).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def windows(ev):
    cp = ev["checkpoints"]
    return {"t_minus_1_start": et_utc(cp["T-1"]), "event_day_start": et_utc(cp["T"]), "release": ev["release"]["utc"],
            "t_plus": {k: et_utc(cp[k], CLOSE) for k in ("T", "T+1", "T+3", "T+5", "T+10")},
            "archive_after": et_utc(tc.add_sessions(date.fromisoformat(cp["T+10"]), 1), CLOSE)}


def pct(x):
    return None if x is None else f"{x * 100:.1f}%"


def action_lines(st, inp):
    y = inp["macro"]["y10"]
    br = inp["breadth"]
    t = st["tranches"]
    lines = []
    s1 = t["1_policy_rate"]["state"]
    lines.append({"tranche": 1, "state": s1, "text": {
        "not_met": f"利率未回落（10Y {y.get('value')}% 截至 {y.get('date')}，作者阈值 5%），第一批条件尚未达成｜暂不追价",
        "unknown": "第一批：事件结果或利率数据待定｜继续观察",
        "candidate": "第一批条件出现（Shadow）｜仍需人工核对预算与风险护栏",
        "conflict_frozen": "风险条件触发｜第一批冻结"}[s1]})
    s2 = t["2_breadth_confirmation"]["state"]
    lines.append({"tranche": 2, "state": s2, "text": {
        "not_met": f"宽度未确认（S&P 500 站上 MA200 {pct(br.get('b200'))}，截至 {br.get('as_of')}）｜第二批继续观察",
        "unknown": f"宽度与确认条件未齐（站上 MA200 {pct(br.get('b200'))}；10Y 未持续低于 5%；12 月 FOMC 未到）｜第二批继续观察",
        "candidate": "第二批确认条件出现（Shadow）｜仍需人工核对预算与风险护栏",
        "conflict_frozen": "风险条件触发｜第二批冻结"}[s2]})
    s3 = t["3_price_levels"]["state"]
    core = inp["core"]
    dd = "、".join(f"{k} 回撤 {pct(-v['drawdown'])}/t1 {pct(v['tiers']['t1'])}" for k, v in sorted(core.items()) if v.get("drawdown") is not None and v.get("tiers"))
    lines.append({"tranche": 3, "state": s3, "text": {
        "not_met": f"核心标的未到既定档位（{dd}）｜不触发",
        "unknown": "价格数据缺失或过期｜第三批无法判断",
        "price_condition_met_needs_manual_budget_and_guardrail_check": "仅现有策略价被触及，第三批观察条件满足｜仍需人工核对预算与风险护栏"}[s3]})
    return lines


def build(now=None):
    now = now or datetime.now(timezone.utc)
    cal = json.loads(bl.EVENTS.read_text(encoding="utf-8"))
    inp = bl.gather(now)
    st = bl.evaluate(inp)
    data = bl._load(bl.DATA)
    expected = inp["expected_session"]
    market_as_of = data.get("spy_date")
    events = []
    for key, ev in sorted(cal["events"].items(), key=lambda kv: kv[1]["release"]["utc"]):
        events.append({"key": key, "name_zh": ev["name_zh"], "importance": ev.get("importance"),
                       "release": ev["release"], "time_status": ev["time_status"], "official_source": ev["official_source"],
                       "checkpoints": ev["checkpoints"], "windows": windows(ev),
                       "official_outcome": ({"recorded_at": ev["official_outcome_recorded_at"], "summary": ev.get("summary")}
                                            if ev.get("official_outcome_recorded_at") else None)})
    freshness = {
        "market_as_of": market_as_of, "expected_session": expected,
        "market_status": "fresh" if market_as_of == expected else ("stale" if market_as_of and market_as_of < expected else "unknown"),
        "y10_as_of": inp["macro"]["y10"].get("date"), "breadth_as_of": inp["breadth"].get("as_of"),
        "data_stale": st["risk_off"]["data_stale"] or market_as_of != expected,
    }
    overall = "data_insufficient" if freshness["data_stale"] else st["overall"]
    return {
        "version": 1, "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "next_scheduled_refresh": "with each Daily Dashboard Update (≈21:30Z / 08:15Z weekdays); event phases update client-side from the clock",
        "stale_after_hours": 36,
        "judgment": {"key": overall, "zh": {"risk_elevated": "偏风险", "neutral_awaiting_confirmation": "中性待确认",
                                             "conditions_improving": "条件改善", "data_insufficient": "数据不足"}[overall],
                     "basis": "MyAlpha Shadow evaluation of the author's tranche rules plus MyAlpha data guards — not the author's forecast"},
        "lines": action_lines(st, inp),
        "risk_off": {"active": st["risk_off"]["active"], "conditions": [{"name": c["name"], "status": c["status"], "rule": c["rule"]} for c in st["risk_off"]["conditions"]]},
        "tranche_state": {k: v["state"] for k, v in st["tranches"].items()},
        "rules_version": st["rules_version"], "freshness": freshness, "events": events,
        "source": {"author": "BrightLine", "title": "别和美联储作对，但底已经不远了", "url": ARTICLE_URL, "analysis_url": ANALYSIS_URL,
                   "reading_basis": "full text read at runtime from the owner-uploaded HTML and verified (SHA256 f909e1b9…); full text not stored",
                   "reading_basis_zh": "已逐句核对全文（owner 上传 HTML，运行时读取，不存全文）",
                   "author_forecast": "约三周内见底 — 可证伪预测，不是事实、买点或收益承诺"},
        "production_use": False, "used_in_decision": False, "automatic_orders": False,
    }


def main():
    out = build()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=Macro event watch::judgment={out['judgment']['key']} market_as_of={out['freshness']['market_as_of']} "
          f"tranches={out['tranche_state']}")


if __name__ == "__main__":
    main()
