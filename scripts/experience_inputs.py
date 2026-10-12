#!/usr/bin/env python3
"""B1 — historical experience as Shadow evidence for automatic research (#133 6116972263 / 6117858510).

Pure functions; daily_research_job attaches the result to each hypothesis. Experience NEVER changes the stance,
the rule view or any weight (used_in_decision=false). Only memory that was already committed when the research ran
is used (in Daily the research step runs before the memory engines, so this is the previous run's memory), and
every case must be matured before both the memory date and the research session.

  precedents        learning_engine.situation_memory[symbol].similarity.matches (5-year causal Trend Pulse event
                    study): matured, 60-session window closed on/before memory date and market_as_of, equity/ETF only
  error_attribution evidence_attribution.failure_attribution — market-derived 20-session attribution hypotheses
                    (no author data): rows for this symbol whose window closed before market_as_of, plus base rates
  excluded          every candidate not used, with why_excluded. method_memory failure examples are always excluded:
                    they derive from unverified author self-reported trades (#205 gate).
"""
from __future__ import annotations
import statistics
from datetime import date

import trading_calendar as tc

NON_EQUITY = {"VIX"}


def _closes(d, n):
    return tc.add_sessions(date.fromisoformat(d), n)


def _side(stance, ret):
    if stance not in ("bullish", "bearish") or ret is None:
        return "context"
    return "supports" if (ret > 0) == (stance == "bullish") else "conflicts"


def build(symbol, stance, market_as_of, mem):
    """mem: {'learning': doc, 'evidence': doc, 'method': doc, 'meta': {name: {'as_of', 'sha256', 'source'}}}"""
    mas = date.fromisoformat(market_as_of)
    meta = mem.get("meta") or {}
    out = {"used_in_decision": False, "memory_inputs": meta, "precedents": [], "excluded": [], "error_attribution": {}}
    learning = mem.get("learning")
    if not learning:
        out["experience_input_status"] = "unknown"
        out["excluded"].append({"source": "situation_memory", "why_excluded": "learning_engine.json unavailable"})
        return out
    sit = next((s for s in learning.get("situation_memory") or [] if s.get("symbol") == symbol), None)
    if sit:
        ts = date.fromisoformat(str(sit.get("timestamp"))[:10])
        if ts > mas:
            out["excluded"].append({"source": "situation_memory", "why_excluded": f"memory dated {ts} is after market_as_of {mas} (look-ahead)"})
        else:
            sim = sit.get("similarity") or {}
            for m in sim.get("matches") or []:
                cid = f"{m.get('symbol')}:{m.get('date')}:{m.get('stage')}"
                why = None
                if m.get("symbol") in NON_EQUITY:
                    why = "non-equity instrument (volatility index) is not a comparable precedent"
                elif m.get("return_60") is None:
                    why = "60-session outcome not matured"
                elif _closes(m["date"], 60) > min(ts, mas):
                    why = "60-session window closes after the memory date / research session (look-ahead)"
                if why:
                    out["excluded"].append({"case_id": cid, "source": "situation_memory", "why_excluded": why})
                    continue
                out["precedents"].append({
                    "case_id": cid, "matched_symbol": m["symbol"], "date": m["date"], "stage": m.get("stage"),
                    "similarity": m.get("similarity"), "return_60": m.get("return_60"), "mae_60": m.get("mae_60"),
                    "outcome_window_closed": str(_closes(m["date"], 60)),
                    "why_matched": f"{sim.get('method') or 'technical similarity'} score {m.get('similarity')} vs {symbol} on {ts} (stage {sit.get('stage')})",
                    "supports_or_conflicts": _side(stance, m.get("return_60")),
                    "memory_as_of": str(ts), "memory_sha256": (meta.get("learning") or {}).get("sha256")})
    else:
        out["excluded"].append({"source": "situation_memory", "why_excluded": f"no situation memory for {symbol}"})
    fa = ((mem.get("evidence") or {}).get("failure_attribution")) or {}
    rows = []
    for r in fa.get("recent") or []:
        if r.get("symbol") != symbol:
            continue
        cid = f"{symbol}:{r.get('date')}:{r.get('source_stage')}"
        if r.get("return_20") is None or _closes(r["date"], 20) > mas:
            out["excluded"].append({"case_id": cid, "source": "failure_attribution", "why_excluded": "20-session window not closed before market_as_of"})
            continue
        rows.append({"case_id": cid, "return_20": r.get("return_20"), "mae_20": r.get("mae_20"), "tags": r.get("tags") or [],
                     "hypothesis": (r.get("attribution_hypotheses") or [None])[0], "basis": "market data only; attribution is a hypothesis, not causation"})
    out["error_attribution"] = {"symbol_cases": rows,
                                "base_rates": {"mature_samples_scanned": fa.get("mature_samples_scanned"), "review_samples": fa.get("review_samples"),
                                               "tag_counts": fa.get("tag_counts"), "scope": "all symbols, 20-session outcomes"},
                                "source_sha256": (meta.get("evidence") or {}).get("sha256")}
    for mm in (mem.get("method") or {}).get("methods") or []:
        for x in mm.get("failure_examples") or []:
            if x.get("symbol") == symbol:
                out["excluded"].append({"case_id": f"method:{mm.get('method')}:{x.get('event_id')}", "source": "method_memory",
                                        "why_excluded": "derived from an unverified author self-reported trade (#205 gate); background only"})
    p = out["precedents"]
    rets = [x["return_60"] for x in p]
    out["summary"] = {"usable_precedents": len(p), "excluded": len(out["excluded"]),
                      "supports": sum(1 for x in p if x["supports_or_conflicts"] == "supports"),
                      "conflicts": sum(1 for x in p if x["supports_or_conflicts"] == "conflicts"),
                      "median_return_60": statistics.median(rets) if rets else None,
                      "positive_rate_60": (sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
                      "symbol_error_cases": len(rows),
                      "note": "descriptive context from matured history; small samples; does not change the stance"}
    out["experience_input_status"] = "used" if (p or rows) else "none"
    return out
