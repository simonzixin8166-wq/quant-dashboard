#!/usr/bin/env python3
"""What kind of drawdown is this? (Owner 2026-11-23: back end only, one Telegram only when the type changes.)

Blogs compare the current fall to 2022 or 1929. The difference between those is not the size of the fall but whether
the financial system itself is breaking. This check reads five official FRED series already in
docs/research/macro_context.json and names the type of drawdown in plain Chinese:

  SYSTEMIC        信用/就业/金融条件出现危机信号（2008、1929 一类）
  TURNING         有体系压力的早期信号，性质可能在变坏
  RATES_VALUATION 利率和估值压力为主，信用和就业平稳（2022 一类）
  ORDINARY        普通回调，体系和利率都没有明显压力
  UNKNOWN         数据不全，不判断

It never forecasts a bottom, never changes thresholds, allocation or orders, and is not shown on the site.
Writes research/regime/drawdown_regime_status.json and appends research/regime/drawdown_regime_history.jsonl
(one row per market date). Telegram: a move to a riskier type is sent at once; a move to a calmer type only after it
held on two consecutive market dates; the first run records a baseline without sending.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MACRO = ROOT / "docs" / "research" / "macro_context.json"
TIERS = ROOT / "docs" / "research" / "core_tier_alert_status.json"
MARKET = ROOT / "docs" / "data.json"     # same-day VIX close (Yahoo); FRED VIXCLS lags one session
OUT = ROOT / "research" / "regime" / "drawdown_regime_status.json"
HISTORY = ROOT / "research" / "regime" / "drawdown_regime_history.jsonl"
VERSION = "drawdown-regime-0.1"
RANK = {"ORDINARY": 0, "RATES_VALUATION": 1, "TURNING": 2, "SYSTEMIC": 3}
LABEL_ZH = {
    "SYSTEMIC": "体系危机型（类似 2008 / 1929）",
    "TURNING": "性质可能在变坏（出现体系压力的早期信号）",
    "RATES_VALUATION": "利率与估值回调型（类似 2022）",
    "ORDINARY": "普通回调",
    "UNKNOWN": "数据不全，暂不判断",
}
# Context only (approximate public peak values; not used in the classification).
ANALOGS = [
    {"episode": "1929-1932", "nasdaq_or_dow_peak_to_trough": "道指约 -89%", "hy_spread_peak": None,
     "unemployment_peak": "约 25%", "note_zh": "银行倒闭、通缩，FRED 无同口径数据"},
    {"episode": "2000-2002", "nasdaq_or_dow_peak_to_trough": "纳指约 -78%", "hy_spread_peak": "约 11%",
     "unemployment_peak": "约 6.3%", "note_zh": "科技估值泡沫破裂叠加衰退"},
    {"episode": "2007-2009", "nasdaq_or_dow_peak_to_trough": "纳指约 -56%", "hy_spread_peak": "约 21.8%",
     "unemployment_peak": "约 10%", "note_zh": "信用体系危机"},
    {"episode": "2020", "nasdaq_or_dow_peak_to_trough": "纳指约 -30%", "hy_spread_peak": "约 10.9%",
     "unemployment_peak": "约 14.8%", "note_zh": "疫情冲击，政策迅速托底"},
    {"episode": "2022", "nasdaq_or_dow_peak_to_trough": "纳指约 -35%", "hy_spread_peak": "约 5.8%",
     "unemployment_peak": "约 3.7%", "note_zh": "加息与实际利率飙升，信用与就业平稳"},
]


def _v(series: dict, sid: str):
    lt = ((series.get(sid) or {}).get("latest") or {})
    return lt.get("value") if isinstance(lt.get("value"), (int, float)) else None


def _chg(series: dict, sid: str, h: str):
    c = ((series.get(sid) or {}).get("changes") or {}).get(h)
    return c if isinstance(c, (int, float)) else None


def checks(macro: dict, market: dict | None = None) -> dict:
    """Five signals, each calm / watch / stress (or unavailable), with the value it was judged on."""
    s = (macro or {}).get("series") or {}
    out = {}
    hy = _v(s, "BAMLH0A0HYM2")
    out["credit"] = {"series": "BAMLH0A0HYM2", "label_zh": "高收益债利差", "value": hy,
                     "level": None if hy is None else ("stress" if hy >= 7 else "watch" if hy >= 5 else "calm"),
                     "rule_zh": "≥5% 警惕，≥7% 危机（2022 峰值约 5.8%，2008 约 21.8%）"}
    un, d3, d20 = _v(s, "UNRATE"), _chg(s, "UNRATE", "3"), _chg(s, "UNRATE", "20")
    lvl = None
    if un is not None and d3 is not None:
        lvl = "stress" if (d3 >= 0.5 or (d20 is not None and d20 >= 1.0)) else "watch" if d3 >= 0.3 else "calm"
    out["jobs"] = {"series": "UNRATE", "label_zh": "失业率", "value": un, "change_3m": d3, "change_20m": d20,
                   "level": lvl, "rule_zh": "3 个月升 ≥0.3 点警惕，≥0.5 点（或 20 个月升 ≥1 点）危机"}
    nf = _v(s, "NFCI")
    out["financial_conditions"] = {"series": "NFCI", "label_zh": "金融条件指数", "value": nf,
                                   "level": None if nf is None else ("stress" if nf >= 0.5 else "watch" if nf >= 0 else "calm"),
                                   "rule_zh": "≥0 偏紧警惕，≥0.5 明显收紧"}
    ry, ry20 = _v(s, "DFII10"), _chg(s, "DFII10", "20")
    out["real_yield"] = {"series": "DFII10", "label_zh": "10 年期实际利率", "value": ry, "change_20d": ry20,
                         "level": None if ry is None else ("stress" if ry >= 2.0 or (ry20 or 0) >= 0.5 else
                                                           "watch" if ry >= 1.5 else "calm"),
                         "rule_zh": "≥1.5% 估值有压力，≥2.0%（或 20 天升 ≥0.5 点）压力大；这是 2022 型下跌的主因"}
    vx, vsrc, vdate = _v(s, "VIXCLS"), "VIXCLS", ((s.get("VIXCLS") or {}).get("latest") or {}).get("date")
    mv = (market or {}).get("vix") if isinstance(market, dict) else None
    if isinstance(mv, dict) and isinstance(mv.get("close"), (int, float)) and str(mv.get("date") or "") > str(vdate or ""):
        vx, vsrc, vdate = round(float(mv["close"]), 2), "yahoo_close", mv["date"]
    out["fear"] = {"series": vsrc, "date": vdate, "label_zh": "恐慌指数 VIX", "value": vx,
                   "level": None if vx is None else ("stress" if vx >= 40 else "watch" if vx >= 30 else "calm"),
                   "rule_zh": "≥30 紧张，≥40 恐慌（只作温度参考，不单独决定类型）"}
    return out


def classify(c: dict) -> str:
    core = [c[k]["level"] for k in ("credit", "jobs", "financial_conditions")]
    if any(x is None for x in core) or c["real_yield"]["level"] is None:
        return "UNKNOWN"
    if c["credit"]["level"] == "stress" or core.count("stress") >= 2 or \
            (c["credit"]["level"] == "watch" and c["jobs"]["level"] == "stress"):
        return "SYSTEMIC"
    if any(x != "calm" for x in core):
        return "TURNING"
    if c["real_yield"]["level"] != "calm":
        return "RATES_VALUATION"
    return "ORDINARY"


def explain(kind: str, c: dict) -> str:
    v = {k: c[k]["value"] for k in c}
    base = (f"信用利差 {v['credit']}%、失业率 {v['jobs']}%、金融条件 {v['financial_conditions']}、"
            f"实际利率 {v['real_yield']}%、VIX {v['fear']}。")
    return {
        "SYSTEMIC": "信用或就业出现危机信号，这类下跌通常更深更久，先保护现金流和杠杆仓位。",
        "TURNING": "信用、就业或金融条件开始变紧，下跌性质可能从估值回调变成体系压力，需要比平时更谨慎。",
        "RATES_VALUATION": "信用和就业平稳，压力主要来自高利率压低科技股估值；历史上这类下跌可以很深，但不是体系崩溃。",
        "ORDINARY": "体系和利率都没有明显压力，属于普通回调。",
        "UNKNOWN": "关键数据缺失，今天不判断。",
    }[kind] + ("" if kind == "UNKNOWN" else " " + base)


def drawdowns() -> dict:
    t = json.loads(TIERS.read_text(encoding="utf-8")) if TIERS.exists() else {}
    return {k: {"drawdown": round(v["drawdown"], 4), "zone": v.get("zone"), "as_of": v.get("as_of")}
            for k, v in (t.get("symbols") or {}).items() if isinstance(v.get("drawdown"), (int, float))}


def _read_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    return [json.loads(x) for x in HISTORY.read_text(encoding="utf-8").splitlines() if x.strip()]


def decide_alert(kind: str, history: list[dict], last_alerted: str | None) -> tuple[bool, str | None]:
    """Send on a move to a riskier type at once; to a calmer type only after two consecutive market dates."""
    if kind == "UNKNOWN":
        return False, last_alerted
    if last_alerted is None:
        return False, kind                        # first run: baseline, no message
    if kind == last_alerted:
        return False, last_alerted
    if RANK[kind] > RANK[last_alerted]:
        return True, kind
    prev = next((h["type"] for h in reversed(history) if h.get("type") != "UNKNOWN"), None)
    return (True, kind) if prev == kind else (False, last_alerted)


def message(kind: str, prev: str, c: dict, dd: dict, as_of: str) -> str:
    worse = RANK[kind] > RANK[prev]
    dds = "；".join(f"{k} {v['drawdown']:.0%}" for k, v in dd.items())
    return (f"MyAlpha｜下跌类型{'升级' if worse else '缓和'}：{LABEL_ZH[prev]} → {LABEL_ZH[kind]}\n"
            f"{explain(kind, c)}\n" + (f"距高点：{dds}。" if dds else "") + f"数据日期 {as_of}。\n"
            "这是提醒，不是买卖指令；不改阈值、不改仓位。")


def notify(text: str) -> str:
    if os.getenv("DRAWDOWN_REGIME_ALERTS_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return "disabled"
    try:
        from daily_guardian import send_telegram
        return send_telegram(text)
    except Exception as exc:  # noqa: BLE001
        return f"failed:{type(exc).__name__}"


def market_vix() -> dict | None:
    try:
        d = json.loads(MARKET.read_text(encoding="utf-8"))
        return {"vix": ((d.get("market_indicators") or {}).get("vix"))}
    except Exception:  # noqa: BLE001
        return None


def run(macro: dict, now: datetime, send=notify, market: dict | None = None) -> dict:
    c = checks(macro, market)
    kind = classify(c)
    as_of = (macro or {}).get("as_of") or now.date().isoformat()
    prev_status = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    last_alerted = prev_status.get("last_alerted_type")
    history = _read_history()
    should, new_alerted = decide_alert(kind, history, last_alerted)
    delivery = send(message(kind, last_alerted, c, drawdowns(), as_of)) if should else None
    if should and delivery not in ("sent", "disabled", "not_configured"):
        new_alerted = last_alerted              # failed: try again on the next run
    rep = {"version": VERSION, "generated_at": now.isoformat(timespec="seconds"), "macro_as_of": as_of,
           "type": kind, "label_zh": LABEL_ZH[kind], "explain_zh": explain(kind, c), "checks": c,
           "drawdowns": drawdowns(), "last_alerted_type": new_alerted,
           "alert": {"sent_now": bool(should), "delivery": delivery}, "analogs_context_only": ANALOGS,
           "production_use": False, "published": False,
           "policy_zh": "只判断下跌的性质，不预测底部；不上网站、不改阈值、不改仓位、不下单。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if not any(h.get("macro_as_of") == as_of for h in history):
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"macro_as_of": as_of, "type": kind, "recorded_at": rep["generated_at"],
                                "values": {k: c[k]["value"] for k in c}}, ensure_ascii=False) + "\n")
    return rep


def main() -> int:
    macro = json.loads(MACRO.read_text(encoding="utf-8")) if MACRO.exists() else {}
    rep = run(macro, datetime.now(timezone.utc), market=market_vix())
    print(json.dumps({"type": rep["type"], "alert": rep["alert"],
                      "levels": {k: v["level"] for k, v in rep["checks"].items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
