#!/usr/bin/env python3
"""Morning brief: one short Telegram message every morning (Owner 2026-11-13: "每天早上给一份简报").

Built only from files the pipelines already publish, so it needs no Claude session and no new data source:
  docs/data.json                           last completed US session: indices, VIX, core ETFs, NVDA etc.
  config/playbooks.public.json             the Owner's core tiers (near / 1 / 2 / 3)
  docs/research/shock_events.json          shock events (corrections applied, retracted ones skipped)
  docs/data/event_calendar.json            macro releases and earnings in the next days
  docs/research/learning_progress.json     the four measures
  docs/research/system_status.json         pipeline health
Data that is late or missing is said plainly ("收盘数据尚未更新"), never filled in.
One brief per Shanghai date (research/store/morning_brief_state.json). Reminder only: no orders, no thresholds.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import core_tier_state as cts  # noqa: E402
import trading_calendar as tc  # noqa: E402

DATA = ROOT / "docs" / "data.json"
TIERS = ROOT / "config" / "playbooks.public.json"
SHOCK = ROOT / "docs" / "research" / "shock_events.json"
CALENDAR = ROOT / "docs" / "data" / "event_calendar.json"
LEARN = ROOT / "docs" / "research" / "learning_progress.json"
STATUS = ROOT / "docs" / "research" / "system_status.json"
OUT = ROOT / "docs" / "research" / "morning_brief.json"
STATE = ROOT / "research" / "store" / "morning_brief_state.json"
SH = ZoneInfo("Asia/Shanghai")
VERSION = "brief-1.0"
CORE = ("QQQM", "VGT", "QLD")
LINE_ZH = {"near": "接近一级", "t1": "一级", "t2": "二级", "t3": "三级"}
DISCLAIMER = "以上是提醒和研究提示，不是买卖指令；是否操作由你决定。"


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def pct(v, sign=True):
    return "—" if v is None else (f"{v:+.1%}" if sign else f"{v:.1%}")


def market_lines(data, expected):
    mi = data.get("market_indicators") or {}
    idx = data.get("index") or {}
    as_of = (idx.get("QQQ") or {}).get("date")
    lines = []
    if as_of != expected:
        lines.append(f"⚠ 美股 {expected} 收盘数据尚未更新（最新 {as_of or '不可用'}），以下为上一交易日。")
    parts = []
    for name, row in (("纳指", mi.get("ixic")), ("标普", mi.get("spx")), ("QQQ", idx.get("QQQ")), ("SMH", idx.get("SMH"))):
        if row and row.get("day_chg") is not None:
            parts.append(f"{name} {pct(row['day_chg'])}")
    vix = mi.get("vix") or {}
    if vix.get("close") is not None:
        parts.append(f"VIX {vix['close']:.1f}（{pct(vix.get('day_chg'))}）")
    lines.append("市场（" + (as_of or "—") + "）：" + ("，".join(parts) if parts else "不可用"))
    return lines, as_of


def core_lines(data, tiers_all):
    lines = []
    for sym in CORE:
        row, tiers = (data.get("core") or {}).get(sym), tiers_all.get(sym)
        loss, ath, why = cts.row_inputs(row, tiers)
        if loss is None:
            lines.append(f"{sym}：不可用（{why}）")
            continue
        th = cts.thresholds(tiers)
        reached = [k for k in ("near", "t1", "t2", "t3") if loss >= th[k]]
        ahead = next((k for k in ("t1", "t2", "t3") if loss < th[k]), None)
        state = f"已到{LINE_ZH[reached[-1]]}线" if reached else "正常区"
        gap = f"，距{LINE_ZH[ahead]} {th[ahead] - loss:.1%}" if ahead else ""
        lines.append(f"{sym} 回撤 {loss:.1%}（{state}{gap}）")
    return lines


def shock_lines(shock, now, data=None):
    rows = []
    for e in (shock or {}).get("events") or []:
        if e.get("retracted"):
            continue
        try:
            seen = datetime.fromisoformat(e["first_seen"])
        except Exception:
            continue
        if now - seen > timedelta(days=3):
            continue
        q = e.get("quote") or {}
        head = e["subject"] if e.get("kind") == "company" else "市场"
        tag = "高" if e.get("severity") == "high" else "中"
        adv = " ".join(e.get("advice") or [])
        if "治理事件" in adv:
            note = "管理层/治理事件，结果未定，等正式公告"
        elif "同期" in adv:
            note = "同行联动，可能与 " + adv.split("同期 ")[1].split(" 也有事件")[0] + " 事件相关（未核实）"
        else:
            note = "原因未核实，不据此调仓"
        ahead = (e.get("upcoming") or [None])[0]
        if ahead:
            note += f"；{ahead['date'][5:].replace('-', '/')} {ahead.get('title_zh') or '已排期事件'}"
        move = pct(q.get("move_total"))
        last = ((data or {}).get("stocks") or {}).get(e["subject"]) or {}
        # the close of the session the event was first seen in (or later) says more than the trigger price
        if e.get("kind") == "company" and last.get("day_chg") is not None and last.get("date", "") >= e["first_seen"][:10]:
            move = f"{last['date'][5:].replace('-', '/')} 收盘 {pct(last['day_chg'])}（发现时 {move}）"
        rows.append(f"[{tag}] {head} {move}：{note}")
    rows.sort(key=lambda r: not r.startswith("[高]"))
    return rows[:4]


def calendar_lines(calendar, today, days=3):
    rows = []
    for e in (calendar or {}).get("events") or []:
        try:
            d = date.fromisoformat(e.get("date", ""))
        except Exception:
            continue
        if today <= d <= today + timedelta(days=days):
            when = "今天" if d == today else d.strftime("%m/%d")
            try:
                t = datetime.fromisoformat(e["datetime"]).astimezone(SH).strftime("北京 %m/%d %H:%M")
            except Exception:
                t = ""
            rows.append(f"{when} {e.get('title_zh')}" + (f"（{t}）" if t else "") + ("（日期非官方）" if e.get("time_status") == "unofficial_date" else ""))
    return rows


def learning_line(learn):
    m = (learn or {}).get("measures") or {}
    u, j, e = m.get("understanding") or {}, m.get("judgments") or {}, m.get("experience") or {}
    prod = u.get("production") or {}
    gem = next((r for r in u.get("rows") or [] if str(r.get("extractor", "")).startswith("gemini")), None)
    h = e.get("h20") or {}
    parts = [f"判断 {j.get('observations', '—')} 条", f"20 日已计分 {h.get('scored', '—')}（命中 {h.get('hits', '—')}）"]
    if prod.get("recall"):
        parts.append(f"生产召回率 {prod['recall']['k']}/{prod['recall']['n']}")
    if gem:
        parts.append(f"Gemini {'已测完' if gem.get('status') == 'complete' else '进行中'}"
                     + (f" {gem['answered_posts']}/85" if gem.get("answered_posts") else ""))
    return f"学习：{(learn or {}).get('learning_state', 'UNPROVEN')}；" + "，".join(parts)


def health_line(status, as_of, expected):
    st = status or {}
    bad = sorted((st.get("active_module_failures") or {}).keys())
    ok = as_of == expected and not bad
    s = "正常" if ok else ("数据未到" if as_of != expected else "有模块失败：" + "、".join(bad[:4]))
    return f"系统：{s}（总体 {st.get('overall', '—')}）"


def build(now=None, data=None, tiers=None, shock=None, calendar=None, learn=None, status=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(SH)
    expected = str(tc.expected_latest_completed_session(now))[:10]
    data = data if data is not None else load(DATA, {})
    tiers = tiers if tiers is not None else (load(TIERS, {}) or {}).get("core_tiers") or {}
    shock = shock if shock is not None else load(SHOCK, {})
    calendar = calendar if calendar is not None else load(CALENDAR, {})
    learn = learn if learn is not None else load(LEARN, {})
    status = status if status is not None else load(STATUS, {})
    mkt, as_of = market_lines(data, expected)
    us_today = local.date()          # the next US session starts this evening Shanghai time
    sections = [f"MyAlpha 早报 · {local:%m/%d} {'一二三四五六日'[local.weekday()]}"]
    sections += mkt
    sections.append("核心：" + "；".join(core_lines(data, tiers)))
    sh = shock_lines(shock, now, data)
    sections.append("突发事件：" + ("无" if not sh else ""))
    sections += [f"· {x}" for x in sh]
    nxt = us_today if tc.is_session(us_today) else tc.next_session(us_today)
    cal = calendar_lines(calendar, us_today)
    sections.append(f"日程（下一交易日 {nxt:%m/%d}）：" + ("；".join(cal) if cal else "未来 3 天无重要排期"))
    sections.append(learning_line(learn))
    sections.append(health_line(status, as_of, expected))
    sections.append(DISCLAIMER)
    text = "\n".join(sections)
    return {"version": VERSION, "generated_at": now.isoformat(timespec="seconds"), "local_date": local.date().isoformat(),
            "expected_session": expected, "data_as_of": as_of, "fresh": as_of == expected, "text": text,
            "production_use": False}


def notify(text):
    if os.getenv("MORNING_BRIEF_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return "disabled"
    from daily_guardian import send_telegram
    return send_telegram(text)


def run(now=None, send=notify, state_path=STATE, out_path=OUT, force=False, **inputs):
    brief = build(now=now, **inputs)
    state = load(state_path, {}) or {}
    day = brief["local_date"]
    prev = state.get(day) or {}
    update = prev.get("status") == "sent" and not prev.get("fresh") and brief["fresh"]
    if prev.get("status") == "sent" and not update and not force:
        brief["delivery"] = "already_sent"
    else:
        if update:
            brief["text"] = brief["text"].replace("MyAlpha 早报", "MyAlpha 早报（收盘数据已更新）", 1)
        d = send(brief["text"])
        brief["delivery"] = d
        state[day] = {"status": "sent" if d == "sent" else d, "fresh": brief["fresh"], "at": brief["generated_at"]}
        state = {k: state[k] for k in sorted(state)[-30:]}
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(state_path).write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    Path(out_path).write_text(json.dumps(brief, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return brief


def main():
    b = run(force="--force" in sys.argv, send=(lambda t: "dry_run") if "--dry-run" in sys.argv else notify)
    print(b["text"])
    print(f"\ndelivery={b['delivery']} fresh={b['fresh']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
