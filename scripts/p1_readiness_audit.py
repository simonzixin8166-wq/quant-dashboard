#!/usr/bin/env python3
"""P1 readiness audit — read-only quality gates before wiring experience into automatic research (#133 6117308392).

Three checks, recomputed from the repository each run (no network, writes research/audit/ only):
  precedents  B1 source = learning_engine.situation_memory[].similarity.matches (5y causal Trend Pulse event study).
              A match is usable at research time only if its 60-session outcome window closed on or before the
              memory's own timestamp (no look-ahead) and the matched instrument is an equity/ETF (VIX excluded).
  outcomes    the six outcome memories: observations, matured outcomes per horizon, duplicates, benchmark history
              availability, earliest possible maturity, contamination (SEC RUB / YTD periods for fundamentals) →
              verdict eligible_for_b2 / pending / insufficient / blocked (+ reason).
  candidates  candidate chain stage counts → keep / freeze recommendation (no deletion).
Output: research/audit/p1_readiness.json
"""
from __future__ import annotations
import hashlib, json, sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

RES, ARCH = ROOT / "docs" / "research", ROOT / "research" / "archive"
OUT = ROOT / "research" / "audit" / "p1_readiness.json"
NON_EQUITY = {"VIX"}
B2_MIN_MATURED = 30  # minimum matured, uncontaminated outcomes per horizon before a memory may inform research


def load(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {} if d is None else d


def jsonl(p):
    p = Path(p)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def sha(p):
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def archive_symbols():
    import zipfile
    z = ROOT / "data" / "history" / "stooq_watchlist.zip"
    if not z.exists():
        return set()
    with zipfile.ZipFile(z) as f:
        return {n.split("_")[0].upper() for n in f.namelist() if n.endswith("_us_d.csv")}


def precedents():
    le = load(RES / "learning_engine.json")
    rows, per_symbol = [], {}
    for s in le.get("situation_memory") or []:
        ts = date.fromisoformat(str(s.get("timestamp"))[:10])
        usable, excluded = [], Counter()
        for m in (s.get("similarity") or {}).get("matches") or []:
            d = date.fromisoformat(m["date"])
            closes = tc.add_sessions(d, 60)
            if m.get("symbol") in NON_EQUITY:
                excluded["non_equity_instrument"] += 1
            elif m.get("return_60") is None:
                excluded["outcome_not_matured"] += 1
            elif closes > ts:
                excluded["look_ahead_window_after_memory_date"] += 1
            else:
                usable.append(m)
        per_symbol[s["symbol"]] = {"memory_timestamp": str(ts), "usable": len(usable), "excluded": dict(excluded),
                                   "similarity_method": (s.get("similarity") or {}).get("method")}
        rows.append((len(usable), excluded))
    tot_ex = Counter()
    for _, e in rows:
        tot_ex.update(e)
    return {"source": "docs/research/learning_engine.json situation_memory[].similarity.matches",
            "source_sha256": sha(RES / "learning_engine.json"), "memory_as_of": le.get("as_of"), "memory_generated_at": le.get("generated_at"),
            "symbols": len(per_symbol), "usable_matches": sum(u for u, _ in rows), "excluded": dict(tot_ex),
            "symbols_with_zero_usable": sorted(k for k, v in per_symbol.items() if v["usable"] == 0),
            "look_ahead_violations": tot_ex.get("look_ahead_window_after_memory_date", 0),
            "timing_note": "in Daily the research step runs before learning_engine_core, so research reads the previous committed memory "
                           "(as_of ≤ market_as_of); B1 must record that memory's as_of and sha256 per precedent",
            "case_id_rule": "historical_journal state-entry event = <symbol>:<date>:<stage>; no native id in the memory",
            "regime_memory": {"historical_matches": (load(RES / "regime_combination_memory.json").get("historical_matches") or {})},
            "method_memory": {"methods": len(load(RES / "method_memory.json").get("methods") or []),
                              "with_direct_validated_events": sum(1 for m in load(RES / "method_memory.json").get("methods") or [] if m.get("direct_validated_events")),
                              "evidence_role": load(RES / "method_memory.json").get("evidence_role")},
            "per_symbol": per_symbol}


def first_maturity(dates, h):
    ds = sorted(d for d in dates if d)
    return str(tc.add_sessions(date.fromisoformat(ds[0]), h)) if ds else None


def outcomes():
    hist = archive_symbols()
    out = {}
    # fundamentals: the only memory with matured outcomes; check SEC contamination found in #203
    fo, fout = jsonl(ARCH / "fundamental_observations.jsonl"), jsonl(ARCH / "fundamental_outcomes.jsonl")
    bad = set()
    for o in fo:
        for name, m in (o.get("metrics") or {}).items():
            if m.get("unit") not in ("USD", "USD/shares", "shares", None):
                bad.add(o["observation_id"])
            if name in ("revenue", "net_income") and m.get("start") and m.get("end"):
                dd = (date.fromisoformat(m["end"]) - date.fromisoformat(m["start"])).days
                if not (80 <= dd <= 100 or 330 <= dd <= 380):
                    bad.add(o["observation_id"])
    clean = [x for x in fout if x["observation_id"] not in bad]
    by_h = Counter(x["horizon_sessions"] for x in clean)
    keys = [(x["observation_id"], x["horizon_sessions"]) for x in fout]
    out["company_fundamental_outcome_memory"] = {
        "observations": len(fo), "matured_outcomes": dict(Counter(x["horizon_sessions"] for x in fout)),
        "duplicate_outcome_keys": len(keys) - len(set(keys)),
        "contaminated_observations": len(bad), "contamination": "non-USD units (NBIS RUB) or YTD revenue/net income periods (#203)",
        "clean_matured_outcomes": dict(by_h),
        "verdict": "eligible_for_b2_clean_subset_only" if min(by_h.get(20, 0), by_h.get(60, 0)) >= B2_MIN_MATURED else "insufficient",
        "conditions": ["use only observations with USD units and quarter/annual periods", "filed date = availability; outcome window starts after filing",
                       "metric values from the old archive stay descriptive until the unified SEC source (B4) re-derives them"]}
    ev = []
    for p in sorted((ARCH / "events").glob("*.jsonl")):
        ev.extend(jsonl(p))
    with_hist = sum(1 for e in ev if e.get("symbol") in hist)
    out["event_outcome_memory"] = {
        "events": len(ev), "matured_outcomes": len(jsonl(ARCH / "event_outcomes.jsonl")),
        "events_with_price_history": with_hist, "events_without_price_history": len(ev) - with_hist,
        "earliest_5_session_maturity": first_maturity([str(e.get("published_at"))[:10] for e in ev], 5),
        "verdict": "pending", "reason": "archive starts 2026-10-06; symbols outside the free price archive can never mature"}
    sv = jsonl(ARCH / "support_volatility_observations" / "2026-10.jsonl")
    out["support_volatility_outcome_memory"] = {"observations": len(sv), "matured_outcomes": 0,
                                                "earliest_20_session_maturity": first_maturity([str(x.get("as_of"))[:10] for x in sv], 20), "verdict": "pending"}
    op = jsonl(ARCH / "options_opportunity_observations" / "2026-10.jsonl")
    out["options_opportunity_outcome_memory"] = {"observations": len(op), "matured_outcomes": 0,
                                                 "earliest_5_session_maturity": first_maturity([str(x.get("as_of"))[:10] for x in op], 5), "verdict": "pending"}
    spy = "SPY" in hist
    mo = jsonl(ARCH / "macro_regime_observations.jsonl")
    out["macro_outcome_memory"] = {"observations": len(mo), "matured_outcomes": 0, "benchmark_history_available": spy,
                                   "verdict": "pending" if spy else "blocked",
                                   "reason": None if spy else "maturation needs SPY daily history, which is absent from data/history/stooq_watchlist.zip → can never mature"}
    ms = {f: len((load(RES / f"{f}.json").get("records") or [])) for f in ("cross_asset_divergence_history", "breadth_intelligence_history", "regime_combination_history")}
    out["market_state_outcome_scorecards"] = {"history_records": ms, "matured_outcomes": 0, "benchmark_history_available": spy,
                                              "verdict": "pending" if spy else "blocked",
                                              "reason": None if spy else "outcomes use anchor_spy and SPY future closes; SPY is absent from the canonical archive"}
    return out


def candidates():
    st = {f.stem: (load(f).get("counts") or {}) for f in sorted(RES.glob("candidate_*.json"))}
    rule = st.get("candidate_rule_status", {})
    fwd = st.get("candidate_forward_status", {})
    rec = {}
    for k in st:
        if k in ("candidate_rule_status", "candidate_parameter_queue", "candidate_rule_replay"):
            rec[k] = "keep (upstream: defines/replays candidates; parameter queue is the real blocker)"
        else:
            rec[k] = "freeze (no candidate is forward-eligible; downstream stages compute empty results)"
    return {"stage_counts": st, "forward_eligible_candidates": fwd.get("eligible_candidates", 0),
            "machine_ready_shadow": rule.get("machine_ready_shadow"), "blocked_needs_definition": rule.get("blocked_needs_definition"),
            "recommendation": rec, "rule": "freeze = stop extending and skip in weekly review; never delete evidence; unfreeze when a candidate becomes forward-eligible"}


def build(now=None):
    now = now or datetime.now(timezone.utc)
    o = outcomes()
    return {"generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "precedents": precedents(), "outcomes": o,
            "outcome_verdicts": {k: v["verdict"] for k, v in o.items()},
            "candidates": candidates(), "b2_min_matured_per_horizon": B2_MIN_MATURED,
            "read_only": True, "production_use": False, "learning_state": "UNPROVEN"}


def main():
    rep = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    p = rep["precedents"]
    print(f"::notice title=P1 readiness::precedents usable={p['usable_matches']} look_ahead={p['look_ahead_violations']} | outcomes {rep['outcome_verdicts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
