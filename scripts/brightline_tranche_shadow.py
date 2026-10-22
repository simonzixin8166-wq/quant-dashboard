#!/usr/bin/env python3
"""R-01 / R-B — BrightLine 8524 "三批进攻" rules as a read-only Shadow state machine (#133 6138763764).

Author rules (v1 from the owner's outline; connectives confirmed against the owner-uploaded full text on
2026-10-13 — the full text itself is never stored) are encoded literally and kept apart from MyAlpha's own
guard rails. Nothing here is a trading signal:
  production_use = false, used_in_decision = false, no orders, no change to CORE_TIERS / DCA / gold / QLD.

Every condition evaluates to met / unmet / unknown. Missing or stale inputs → unknown (fail-closed); a date
arriving never satisfies a condition by itself. The connective of each author branch (AND / OR) is stored
next to the rule, with its provenance, so it can be corrected once the full text is reviewed.

Allocation: the author invests only cash ABOVE his own 20 % cash floor, in three tranches without stated
sizes. MyAlpha records allocation_unset — it never infers 1/3 per tranche and never applies the author's
20 % floor to the owner.
"""
from __future__ import annotations
import json, sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

RULES_VERSION = "bl8524-tranche-v1.2"  # v1.2: an outcome whose surprise is unknown (consensus unavailable) stays unknown, never unmet
RULES_LOCKED_AT = "2026-10-13T16:00:00Z"  # locked before the 10/14 CPI release; v1.1 2026-10-13T06:35:00Z, v1 06:00:00Z
SURPRISE_LABELS = ("soft", "inline", "above", "hot")  # set only from a preregistered consensus of the SAME measure (m/m vs m/m, y/y vs y/y)
OUT = ROOT / "research" / "macro_events" / "brightline_three_tranche_state.json"
MACRO = ROOT / "docs" / "research" / "macro_context.json"
BREADTH = ROOT / "docs" / "research" / "breadth_intelligence.json"
DATA = ROOT / "docs" / "data.json"
EVENTS = ROOT / "research" / "macro_events" / "event_facts_2026q4.json"  # official outcomes, appended after each event

AUTHOR_THRESHOLDS = {"y10_below": 5.00, "y10_risk_line": 5.35, "spx_above_ma200_share": 0.50}
MAX_STALE_SESSIONS = {"macro": 3, "breadth": 2, "price": 2}
SOURCE_NOTE = ("full text verified 2026-10-13 (owner-uploaded HTML sha256 bd834014…; 50 paragraphs; normalized sha256 f909e1b9…); "
               "connectives read from paragraphs 43–46; v1 was based on the owner outline")


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def stale(as_of, expected, kind):
    """True when as_of is missing or more than MAX_STALE_SESSIONS[kind] NYSE sessions behind expected."""
    if not as_of:
        return True
    try:
        lag = len(tc.sessions_between(str(as_of)[:10], str(expected)[:10]))
    except Exception:
        return True
    return lag > MAX_STALE_SESSIONS[kind]


def cond(name, status, value=None, as_of=None, rule=None, note=None, threshold_kind=None):
    assert status in ("met", "unmet", "unknown")
    out = {"name": name, "status": status, "value": value, "as_of": as_of, "rule": rule, "note": note}
    if threshold_kind:
        out["threshold_kind"] = threshold_kind
    return out


def combine(kind, items):
    """AND/OR with unknown propagation (Kleene logic): never upgrades unknown to met."""
    st = [c["status"] for c in items]
    if kind == "AND":
        return "unmet" if "unmet" in st else ("unknown" if "unknown" in st else "met")
    return "met" if "met" in st else ("unknown" if "unknown" in st else "unmet")


def event_fact(events, key):
    """Official outcome of a dated event, recorded only after it happens (never inferred from the date)."""
    e = (events.get("events") or {}).get(key) or {}
    return e if e.get("official_outcome_recorded_at") else None


def surprise_status(e, target):
    """met/unmet only when the official outcome carries a consensus-based surprise label; otherwise unknown
    (an official value alone, a single bank forecast or a nowcast never defines 'soft'/'hot')."""
    if not e or e.get("surprise") not in SURPRISE_LABELS:
        return "unknown"
    return "met" if e["surprise"] == target else "unmet"


def evaluate(inputs):
    """inputs: {'expected_session', 'macro': {'y10': {'value','date','change_20'}}, 'breadth': {'b200','as_of','new_low_52w_pct','new_low_trend'},
    'events': {...}, 'core': {sym: {'drawdown','date','tiers'}}}"""
    exp = inputs["expected_session"]
    y10 = (inputs.get("macro") or {}).get("y10") or {}
    y10_ok = y10.get("value") is not None and not stale(y10.get("date"), exp, "macro")
    br = inputs.get("breadth") or {}
    br_ok = br.get("b200") is not None and not stale(br.get("as_of"), exp, "breadth")
    ev = inputs.get("events") or {}

    # --- risk_off (author's stop conditions for tranches 1–2) + MyAlpha data-quality guard -------------
    cpi = event_fact(ev, "cpi_2026_09")
    fomc = event_fact(ev, "fomc_2026_10")
    risk = [
        cond("cpi_well_above_expectations", surprise_status(cpi, "hot"),
             value=(cpi or {}).get("summary"), as_of=(cpi or {}).get("official_outcome_recorded_at"),
             rule="author (p46): CPI 爆表 → 前两批继续等", note=None if cpi and cpi.get("surprise") in SURPRISE_LABELS else
             ("official outcome recorded; consensus_unavailable → surprise unknown" if cpi else "event not yet released / outcome not recorded")),
        cond("fomc_october_surprise_hike", "unknown" if not fomc else ("met" if fomc.get("hiked") else "unmet"),
             value=(fomc or {}).get("summary"), as_of=(fomc or {}).get("official_outcome_recorded_at"),
             rule="author (p46): 10 月底意外加息 → 前两批继续等", note=None if fomc else "event not yet released / outcome not recorded"),
        cond("y10_above_author_risk_line", "unknown" if not y10_ok else ("met" if y10["value"] > AUTHOR_THRESHOLDS["y10_risk_line"] else "unmet"),
             value=y10.get("value"), as_of=y10.get("date"), rule="author (p46): 10 年期突破 5.35% → 前两批继续等",
             threshold_kind="author_threshold"),
    ]
    data_stale = not (y10_ok and br_ok)
    risk_off_active = any(c["status"] == "met" for c in risk)
    freeze_1_2 = risk_off_active or data_stale

    # --- Tranche 1: policy / rate ------------------------------------------------------------------------
    refund = event_fact(ev, "treasury_refunding_2026_11_04")
    y10_turn = (cond("y10_trend_turns_down", "unknown", as_of=y10.get("date"), note="10Y missing or stale")
                if not y10_ok or y10.get("change_20") is None else
                cond("y10_trend_turns_down", "met" if y10["change_20"] < 0 else "unmet", value=y10.get("change_20"), as_of=y10.get("date"),
                     rule="MyAlpha operationalisation: 20-session change of DGS10 < 0 (author: 收益率趋势掉头向下)"))
    t1_main = [cond("refunding_shortens_or_cuts_long_auctions",
                    "unknown" if not refund else ("met" if refund.get("shorter_or_fewer_long") else "unmet"),
                    value=(refund or {}).get("summary"), as_of=(refund or {}).get("official_outcome_recorded_at"),
                    rule="author (p43): 11/4 季度再融资把发行转向短债，或者削减长债拍卖（官方文本）",
                    note=None if refund else "2026-11-04 not yet happened; the date alone never satisfies this"),
               y10_turn]
    t1_early = [cond("cpi_soft", surprise_status(cpi, "soft"),
                     value=(cpi or {}).get("summary"), as_of=(cpi or {}).get("official_outcome_recorded_at"), rule="author (p43): 这周三（10/14）CPI 偏软"),
                cond("y10_below_author_5pct", "unknown" if not y10_ok else ("met" if y10["value"] < AUTHOR_THRESHOLDS["y10_below"] else "unmet"),
                     value=y10.get("value"), as_of=y10.get("date"), rule="author (p43): 10Y 直接跌破 5%", threshold_kind="author_threshold")]
    t1 = combine("OR", [{"status": combine("AND", t1_main)}, {"status": combine("AND", t1_early)}])

    # --- Tranche 2: breadth / confirmation --------------------------------------------------------------
    if not y10_ok:
        sus = "unknown"
    elif y10["value"] >= AUTHOR_THRESHOLDS["y10_below"]:
        sus = "unmet"
    elif y10.get("max_10") is None:
        sus = "unknown"  # below 5 % today, but "持续" cannot be shown without history
    else:
        sus = "met" if y10["max_10"] < AUTHOR_THRESHOLDS["y10_below"] else "unmet"
    y10_sustained = cond("y10_sustained_below_author_5pct", sus,
                         value={"latest": y10.get("value"), "max_10": y10.get("max_10")}, as_of=y10.get("date"),
                         rule="author: 10Y 持续稳在 5% 下方 (MyAlpha: latest and 10-session max < 5%)", threshold_kind="author_threshold",
                         note=None if y10.get("max_10") is not None or not y10_ok else "10-session history unavailable")
    laggards = cond("laggards_stop_new_lows",
                    "unknown" if not br_ok or br.get("new_low_trend") is None else ("met" if br["new_low_trend"] == "falling" else "unmet"),
                    value={"new_low_52w_pct": br.get("new_low_52w_pct"), "trend": br.get("new_low_trend")}, as_of=br.get("as_of"),
                    rule="author: 掉队股不再创新低 (MyAlpha: S&P 500 52w-new-low share falling over 10 sessions)",
                    note="trend needs ≥10 sessions of stored breadth history" if br.get("new_low_trend") is None else None)
    b200 = cond("spx_share_above_ma200_gt_50pct", "unknown" if not br_ok else ("met" if br["b200"] > AUTHOR_THRESHOLDS["spx_above_ma200_share"] else "unmet"),
                value=br.get("b200"), as_of=br.get("as_of"), rule="author (p44): S&P 500 站上 200 日均线的股票比例重新回到一半以上",
                threshold_kind="author_threshold", note=f"MyAlpha own breadth from S&P 500 constituents (coverage {br.get('coverage')}/{br.get('universe')}); never IWM/SPY proxy")
    dec = event_fact(ev, "fomc_2026_12")
    t2_alt = cond("december_fomc_signals_last_hike", "unknown" if not dec else ("met" if dec.get("signals_last_hike") else "unmet"),
                  value=(dec or {}).get("summary"), as_of=(dec or {}).get("official_outcome_recorded_at"), rule="author (p44): 或者 12 月议息会议暗示这是最后一次加息（替代分支）")
    t2 = combine("OR", [{"status": combine("AND", [y10_sustained, laggards, b200])}, t2_alt])

    # --- Tranche 3: pre-computed price levels (author did not publish his); MyAlpha links EXISTING tiers only
    t3_items = []
    for sym, c in sorted((inputs.get("core") or {}).items()):
        if c.get("drawdown") is None or stale(c.get("date"), exp, "price"):
            t3_items.append(cond(f"{sym}_existing_tier1_reached", "unknown", as_of=c.get("date"), note="price missing or stale"))
            continue
        t1lvl = (c.get("tiers") or {}).get("t1")
        t3_items.append(cond(f"{sym}_existing_tier1_reached", "met" if -c["drawdown"] >= t1lvl else "unmet",
                             value={"drawdown": round(c["drawdown"], 4), "existing_t1": t1lvl}, as_of=c.get("date"),
                             rule="MyAlpha: existing CORE_TIERS t1 drawdown (read-only link; author's own levels were not published)"))
    t3 = combine("OR", t3_items) if t3_items else "unknown"

    def tranche(status, frozen):
        if frozen and status == "met":
            return "conflict_frozen"
        return {"met": "candidate", "unmet": "not_met", "unknown": "unknown"}[status]

    t1_state = tranche(t1, freeze_1_2)
    t2_state = tranche(t2, freeze_1_2)
    t3_state = {"met": "price_condition_met_needs_manual_budget_and_guardrail_check", "unmet": "not_met", "unknown": "unknown"}[t3]
    if data_stale:
        overall = "data_insufficient"
    elif risk_off_active:
        overall = "risk_elevated"
    elif "candidate" in (t1_state, t2_state):
        overall = "conditions_improving"
    else:
        overall = "neutral_awaiting_confirmation"
    return {
        "rules_version": RULES_VERSION, "rules_locked_at": RULES_LOCKED_AT, "expected_session": exp,
        "overall": overall,
        "overall_zh": {"risk_elevated": "偏风险", "neutral_awaiting_confirmation": "中性待确认",
                       "conditions_improving": "条件改善", "data_insufficient": "数据不足"}[overall],
        "risk_off": {"active": risk_off_active, "data_stale": data_stale, "freezes_tranches": [1, 2] if freeze_1_2 else [],
                     "conditions": risk},
        "tranches": {
            "1_policy_rate": {"state": t1_state, "connective": "(refunding AND y10_turn) OR (cpi_soft AND y10<5%)",
                              "connective_source": SOURCE_NOTE, "main": t1_main, "early": t1_early},
            "2_breadth_confirmation": {"state": t2_state, "connective": "(y10 sustained<5% AND laggards stop AND b200>50%) OR december_fomc_last_hike",
                                       "connective_source": SOURCE_NOTE, "main": [y10_sustained, laggards, b200], "alternative": [t2_alt]},
            "3_price_levels": {"state": t3_state, "conditions": t3_items,
                               "note": "independent of tranches 1–2 per the author; MyAlpha still requires manual budget and total-risk guardrails"},
        },
        "allocation": {"status": "allocation_unset", "author_cash_floor": "author's own 20 % — NOT applied to the owner",
                       "tranche_sizes": "not stated by the author — never inferred",
                       "author_budget_rule": "p42: only cash above the author's 20 % floor; after all three tranches cash returns exactly to 20 %"},
        "author_defensive_rules_not_applied": [
            "p36 先砍 2 倍杠杆 ETF 与短期期权（时间衰减）", "p37 太重的仓位在反弹中减，不在恐慌中砍", "p38 不追已在高位的巨头",
            "p39 现金放短期国债（约 4%）", "p40 20% 现金底线任何时候不动"],
        "author_defensive_rules_note": "author's personal rules — recorded for research only; QQQM/VGT core, QLD rules, gold, DCA and the owner's allocation are unchanged",
        "used_in_decision": False, "production_use": False, "automatic_orders": False,
    }


def gather(now=None):
    exp = tc.expected_latest_completed_session(now).isoformat()
    m = (_load(MACRO).get("series") or {}).get("DGS10") or {}
    lat = m.get("latest") or {}
    y10 = {"value": lat.get("value"), "date": lat.get("date"), "change_20": (m.get("changes") or {}).get("20"), "max_10": None}
    b = _load(BREADTH)
    met = b.get("metrics") or b.get("current") or {}
    breadth = {"b200": met.get("b200"), "as_of": b.get("as_of"), "new_low_52w_pct": met.get("new_low_52w_pct"),
               "new_low_trend": None, "coverage": met.get("coverage"), "universe": met.get("universe")}
    d = _load(DATA)
    core = {s: {"drawdown": (d.get("core") or {}).get(s, {}).get("drawdown"), "date": (d.get("core") or {}).get(s, {}).get("date"),
                "tiers": (d.get("core") or {}).get(s, {}).get("tiers")} for s in ("QQQM", "VGT")}
    return {"expected_session": exp, "macro": {"y10": y10}, "breadth": breadth, "events": _load(EVENTS), "core": core}


def main():
    now = datetime.now(timezone.utc)
    st = evaluate(gather(now))
    st["generated_at"] = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    st["inputs"] = {"macro": str(MACRO.relative_to(ROOT)), "breadth": str(BREADTH.relative_to(ROOT)), "prices": str(DATA.relative_to(ROOT)),
                    "events": str(EVENTS.relative_to(ROOT))}
    OUT.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"overall": st["overall"], "t1": st["tranches"]["1_policy_rate"]["state"],
                      "t2": st["tranches"]["2_breadth_confirmation"]["state"], "t3": st["tranches"]["3_price_levels"]["state"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
