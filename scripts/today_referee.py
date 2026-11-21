#!/usr/bin/env python3
"""S4-1 · Today's Action referee (shadow). Owner-approved plan v0.2, 2026-11-21.

One referee condenses the conclusions the pipelines already publish into: at most 3 action cards, a folded
watch list, a one-line hold summary, and an explicit page mode. The mode is one of:
  ACTION        at least one action today
  NO_ACTION     data trusted, nothing to do today ("今天无需操作")
  CANNOT_JUDGE  the data the actions depend on is not trusted ("无法判断")

Shadow: writes docs/research/today_actions.json and appends research/archive/today_actions.jsonl. Nothing reads
them yet; the home page and morning brief switch to this output only in S4-3. Reminders only: no orders, no
quantities, no threshold or allocation changes. The public file carries public market-level items only. Private
option actions stay on the private channel, and the public page shows no private count (Owner 2026-11-21).

Priority (roadmap 10/08): data trust > hard risk > held-position risk > thesis invalidation > formal trigger
(core tiers, DCA) > fundamentals > technicals > validated methods (0 today) > external research > media.
Every action card carries evidence with as_of, counter-evidence and a falsifiable invalidation condition.
A card missing a safety field is marked NEEDS_VERIFICATION. It is never downgraded or dropped.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

R = ROOT / "docs" / "research"
OUT = R / "today_actions.json"
LOG = ROOT / "research" / "archive" / "today_actions.jsonl"
VERSION = "today-referee-0.1"
MAX_ACTIONS, MAX_WATCH = 3, 5
LINE_ZH = {"near": "接近线", "t1": "一级", "t2": "二级", "t3": "三级"}
PRIORITY = {"hard_risk": 1, "position_risk": 2, "thesis": 3, "formal_trigger": 4, "fundamental": 5,
            "technical": 6, "validated_method": 7, "external": 8, "media": 9}
SAFETY_FIELDS = ("evidence", "as_of", "data_trusted")
PUBLIC_CARD_FIELDS = ("level", "action", "symbol", "title_zh", "reason_zh", "evidence", "counter_evidence_zh",
                      "invalidation_zh", "as_of", "source_module", "category", "priority", "dedup_key",
                      "status", "first_seen", "valid_until", "verification", "certainty_zh", "position_zh")


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_inputs(root: Path = ROOT) -> dict:
    r = root / "docs" / "research"
    return {"core": _read(r / "core_tier_alert_status.json"), "review": _read(r / "threshold_review.json"),
            "data": _read(root / "docs" / "data.json"), "invest": _read(r / "investment_actions_status.json"),
            "playbooks": _read(r / "playbook_status.json"), "shock": _read(r / "shock_events.json"),
            "turning": _read(r / "turning_point_checklist.json"), "system": _read(r / "system_status.json")}


def _pct(x) -> str:
    return f"{abs(x) * 100:.1f}%"


def _card(level, action, symbol, category, title, reason, evidence, counter, invalidation, as_of, module,
          trusted, valid_until=None, position=None):
    c = {"level": level, "action": action, "symbol": symbol, "category": category, "priority": PRIORITY[category],
         "title_zh": title, "reason_zh": reason, "evidence": evidence, "counter_evidence_zh": counter,
         "invalidation_zh": invalidation, "as_of": as_of, "source_module": module, "data_trusted": trusted,
         "valid_until": valid_until, "position_zh": position,
         "certainty_zh": "规则提醒，方法未经前瞻验证（已验证方法 0 个）"}
    c["dedup_key"] = f"{symbol}|{module}|{action}|{as_of}"
    missing = [f for f in SAFETY_FIELDS if not c.get(f)]
    c["verification"] = "NEEDS_VERIFICATION" if missing else "OK"
    if missing:
        c["missing_safety_fields"] = missing
    return c


# ---------- candidate builders (each returns cards for its own source; data trust is decided per source) ----------

def core_candidates(core: dict | None, review: dict | None, session: str) -> tuple[list, list, dict]:
    """New tier entries/re-entries of this session -> ACTION; symbols resting in a tier -> hold line."""
    acts, holds, trust = [], [], {"module": "core_tier_alert", "ok": False, "as_of": None}
    if not core:
        trust["reason"] = "missing"
        return acts, holds, trust
    exp = core.get("expected_session")
    trust.update(as_of=exp, ok=exp == session)
    if not trust["ok"]:
        trust["reason"] = f"core tiers judged {exp}, expected {session}"
        return acts, holds, trust
    rev = (review or {}).get("symbols") or {}
    todays = [e for e in core.get("events") or [] if e.get("as_of") == session and e.get("kind") in ("enter", "reenter")
              and e.get("line") in ("t1", "t2", "t3")]
    for sym, s in (core.get("symbols") or {}).items():
        if s.get("judgment") != "evaluated" or s.get("as_of") != session:
            continue
        th, dd, zone = s.get("thresholds") or {}, float(s.get("drawdown") or 0), s.get("zone")
        nxt = next((ln for ln in ("t1", "t2", "t3") if abs(dd) < th.get(ln, 9)), None)
        to_next = f"距{LINE_ZH[nxt]}（{_pct(th[nxt])}）还差 {(th[nxt] - abs(dd)) * 100:.1f} 个百分点" if nxt else "已过三级线"
        ev = [e for e in todays if e["symbol"] == sym]
        if not ev:
            if zone in ("t1", "t2", "t3"):
                holds.append(f"{sym} 仍在{LINE_ZH[zone]}（回撤 {_pct(dd)}），{to_next}")
            continue
        e = max(ev, key=lambda x: ("t1", "t2", "t3").index(x["line"]))
        line = e["line"]
        st = (((rev.get(sym) or {}).get("historical_replay") or {}).get("stats") or {}).get(line) or {}
        if st.get("entries"):
            med, worst = abs(st.get("median_deepest_drawdown") or 0), abs(st.get("deepest_ever") or 0)
            vs = ("已比历史最深一次更深" if abs(dd) > worst else "已深于历史中位" if abs(dd) > med else "仍浅于历史中位")
            counter = (f"历史回放：{sym} 进入{LINE_ZH[line]} {st['entries']} 次，最深回撤中位 {_pct(med)}、最深 {_pct(worst)}；"
                       f"本轮 {_pct(dd)}，{vs}。60 日后为正 {st.get('positive_60', '?')}。回放不是前瞻证据，下跌可能继续。")
        else:
            counter = f"{sym} 进入{LINE_ZH[line]}的历史样本不足，无法给出回放参考；下跌可能继续。"
        leave = th.get(line, 0) - (core.get("leave_buffer_pp") or 0.02)
        kind_zh = "再次跌破" if e["kind"] == "reenter" else "进入"
        acts.append(_card(
            "ACTION", "TIER_REMINDER", sym, "formal_trigger",
            f"{sym} {kind_zh}{LINE_ZH[line]}（回撤 {_pct(dd)}）",
            f"按你的分档计划，{sym} 已到{LINE_ZH[line]}加仓线 {_pct(th.get(line, 0))}；是否加仓、加多少由你决定。",
            [{"source": "docs/research/core_tier_alert_status.json", "as_of": session, "key": e.get("key")},
             {"source": "docs/research/threshold_review.json", "as_of": (review or {}).get("generated_at", "")[:10]}],
            counter,
            f"收盘回撤回到 {_pct(leave)} 以内 → 本提醒结束（离开{LINE_ZH[line]}）；跌破{LINE_ZH.get(nxt, '下一档')}会另发提醒。",
            session, "core_tier_alert", True, valid_until=session,
            position=f"回撤 {_pct(dd)}，{to_next}"))
    return acts, holds, trust


def tqqq_candidates(data: dict | None, session: str) -> tuple[list, list, dict]:
    acts, holds, trust = [], [], {"module": "tqqq_x2", "ok": False, "as_of": None}
    x = (data or {}).get("tqqq_x2") or {}
    if not x.get("available"):
        trust["reason"] = "unavailable"
        return acts, holds, trust
    trust.update(as_of=x.get("date"), ok=x.get("date") == session)
    if not trust["ok"]:
        trust["reason"] = f"tqqq_x2 dated {x.get('date')}, expected {session}"
        return acts, holds, trust
    rule, label = x.get("rule"), x.get("status_label") or ""
    if x.get("changed"):
        hard = rule == "hard_exit"
        acts.append(_card(
            "ACTION", "EXIT" if hard else "STATE_CHANGE", "TQQQ", "hard_risk" if hard else "position_risk",
            f"TQQQ X2 状态变化：{x.get('action')}",
            f"受保护规则 TQQQ X2 今日切换到「{label}」，目标仓位 {x.get('target_position')}%。",
            [{"source": "docs/data.json::tqqq_x2", "as_of": session}],
            "这是风险规则的状态切换，不是对涨跌的预测；规则本身尚未经过前瞻验证。",
            "下一交易日规则回到持有或其他状态 → 本提醒被新状态取代。",
            session, "tqqq_x2", True, valid_until=session))
    elif rule:
        holds.append(f"TQQQ X2 维持「{label}」（目标仓位 {x.get('target_position')}%）")
    return acts, holds, trust


def dca_candidates(invest: dict | None, today_sh: str) -> tuple[list, list, dict]:
    acts, holds, trust = [], [], {"module": "dca_calendar", "ok": False, "as_of": None}
    cal = (invest or {}).get("dca_calendar") or {}
    months = cal.get("months") or []
    if not months:
        trust["reason"] = "missing"
        return acts, holds, trust
    trust.update(ok=True, as_of=today_sh)
    syms = "、".join(cal.get("symbols") or [])
    cur = next((m for m in months if m.get("due_date") and m["due_date"] <= today_sh <= (m.get("window_end") or m["due_date"])), None)
    if cur:
        acts.append(_card(
            "ACTION", "DCA_REMINDER", "DCA", "formal_trigger", f"本月定投提醒（{cur['month']}）",
            f"按定投日历，{syms} 本月定投窗口 {cur['due_date']}–{cur.get('window_end')}。",
            [{"source": "docs/research/investment_actions_status.json::dca_calendar", "as_of": today_sh}],
            "定投不择时；是否调整金额由你决定，本提醒不给金额。",
            f"窗口结束（{cur.get('window_end')}）→ 本提醒结束。", today_sh, "dca_calendar", True,
            valid_until=cur.get("window_end")))
    else:
        nxt = next((m for m in months if (m.get("due_date") or "") > today_sh), None)
        if nxt:
            holds.append(f"定投按日历执行，下次 {nxt['due_date']}")
    return acts, holds, trust


def watch_candidates(inp: dict, session: str) -> list[dict]:
    """Media, external views and non-validated signals: at most WATCH, never an action on their own."""
    out = []
    g = ((inp.get("invest") or {}).get("gold")) or {}
    if g.get("state") in ("REVIEW", "WATCH"):
        out.append({"level": "WATCH", "symbol": "GOLD", "category": "formal_trigger", "priority": 4,
                    "title_zh": f"黄金分批：{'；'.join(g.get('reasons') or [])}", "source_module": "gold_dca",
                    "as_of": ((g.get("quote") or {}).get("as_of") or "")[:10]})
    for p in ((inp.get("playbooks") or {}).get("playbooks") or []):
        if p.get("playbook_id") == "CP-03" and p.get("state") == "TRIGGERED" and p.get("market_date") == session:
            out.append({"level": "WATCH", "symbol": p.get("symbol"), "category": "technical", "priority": 6,
                        "title_zh": f"{p.get('symbol')} 反弹候选（CP-03，规则未验证）", "source_module": "playbook_CP-03",
                        "as_of": session})
    # shock events detected during this session (an intraday event's ref_session is the previous close)
    for e in ((inp.get("shock") or {}).get("events") or []):
        if str(e.get("first_seen") or "")[:10] < session or e.get("ref_session", "") > session:
            continue
        if any(c.get("retracted") for c in e.get("corrections") or []):
            continue
        q = e.get("quote") if isinstance(e.get("quote"), dict) else {}
        mv = q.get("move_total")
        out.append({"level": "WATCH", "symbol": e.get("subject"), "category": "media", "priority": 9,
                    "title_zh": f"突发：{e.get('subject')}" + (f" {mv * 100:+.1f}%" if isinstance(mv, (int, float)) else "")
                    + "（原因未核实）", "source_module": "shock_event_watch", "as_of": session,
                    "severity": e.get("severity")})
    t = inp.get("turning") or {}
    if t.get("market_date") == session:
        s = t.get("summary") or {}
        out.append({"level": "WATCH", "symbol": "MARKET", "category": "external", "priority": 8,
                    "title_zh": f"变盘清单（外部观点，未验证）：{s.get('headline')}", "source_module": "turning_point_checklist",
                    "as_of": session, "triggered": bool(s.get("triggered"))})
    out.sort(key=lambda w: (w["priority"], 0 if w.get("severity") == "high" else 1))
    return out


# ---------- the referee ----------

def referee(inp: dict, session: str, today_sh: str, history: list[dict] | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    history = history or []
    a1, h1, t1 = tqqq_candidates(inp.get("data"), session)
    a2, h2, t2 = core_candidates(inp.get("core"), inp.get("review"), session)
    a3, h3, t3 = dca_candidates(inp.get("invest"), today_sh)
    trust = [t1, t2, t3]
    actions = a1 + a2 + a3
    # dedupe: one card per symbol per day, highest priority wins; the rest become supporting evidence
    by_sym: dict[str, dict] = {}
    for c in sorted(actions, key=lambda c: c["priority"]):
        if c["symbol"] in by_sym:
            by_sym[c["symbol"]].setdefault("supporting", []).append(c["title_zh"])
        else:
            by_sym[c["symbol"]] = c
    actions = sorted(by_sym.values(), key=lambda c: (c["priority"], c["symbol"]))
    # lifecycle: a dedup_key seen in an earlier run keeps its first_seen and becomes ACTIVE
    seen = {}
    for row in history:
        for c in row.get("actions") or []:
            seen.setdefault(c.get("dedup_key"), c.get("first_seen"))
    stamp = now.isoformat(timespec="seconds")
    for c in actions:
        c["first_seen"] = seen.get(c["dedup_key"]) or stamp
        c["status"] = "ACTIVE" if c["dedup_key"] in seen else "NEW"
    blocked = [t for t in trust if not t["ok"]]
    core_ok = next(t for t in trust if t["module"] == "core_tier_alert")["ok"]
    if not core_ok and not actions:
        mode, headline = "CANNOT_JUDGE", "无法判断：核心分档所依赖的收盘数据不是最新，今天不给任何行动。"
    elif actions:
        mode, headline = "ACTION", f"今天有 {len(actions)} 条需要你看的提醒" + ("（另有部分数据未更新，见下方）" if blocked else "")
    else:
        mode, headline = "NO_ACTION", "今天无需操作：核心未到新档位，非定投日，无硬风险变化。"
    shown, overflow = actions[:MAX_ACTIONS], actions[MAX_ACTIONS:]
    watch = []
    for w in watch_candidates(inp, session):      # a symbol with an action card shows it as supporting evidence
        card = next((c for c in shown if c["symbol"] == w["symbol"]), None)
        if card:
            card.setdefault("supporting", []).append(w["title_zh"])
        else:
            watch.append(w)
    public = [{k: c.get(k) for k in PUBLIC_CARD_FIELDS} | ({"supporting_zh": c["supporting"]} if c.get("supporting") else {})
              for c in shown]
    out = {"version": VERSION, "generated_at": stamp, "session": session, "local_date": today_sh, "mode": mode,
           "headline_zh": headline, "actions": public,
           "overflow": {"count": len(overflow), "items": [{"symbol": c["symbol"], "title_zh": c["title_zh"]} for c in overflow]},
           "watch": {"count": len(watch), "items": watch[:MAX_WATCH], "folded": max(0, len(watch) - MAX_WATCH)},
           "hold_zh": "；".join(h1 + h2 + h3) or "无持有类摘要",
           "data_trust": {"blocked": [{"module": t["module"], "reason": t.get("reason")} for t in blocked],
                          "inputs": [{k: t.get(k) for k in ("module", "ok", "as_of")} for t in trust]},
           "shadow": True, "production_use": False,
           "policy_zh": "提醒和研究提示，不是买卖指令；不下单、不给数量、不改阈值。私有期权行动不在公开文件中。"}
    out["content_sha"] = hashlib.sha256(json.dumps({k: out[k] for k in ("session", "mode", "actions", "overflow", "watch", "hold_zh")},
                                                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return out


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    import trading_calendar as tc
    session = tc.expected_latest_completed_session().isoformat()
    today_sh = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    history = read_jsonl(LOG)
    out = referee(load_inputs(), session, today_sh, history)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if not history or history[-1].get("content_sha") != out["content_sha"]:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({k: out[k] for k in ("session", "mode", "headline_zh")} | {"actions": [a["title_zh"] for a in out["actions"]],
                                                                               "overflow": out["overflow"]["count"],
                                                                               "watch": out["watch"]["count"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
