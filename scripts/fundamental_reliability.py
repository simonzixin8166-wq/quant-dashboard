#!/usr/bin/env python3
"""B2-02 — historical reliability context for SEC revenue-YoY evidence (#133 6116972263 / 6117308392).

Only the clean fundamentals-outcome subset is used (same rule as p1_readiness_audit): USD units and
quarter (80–100 days) or annual (330–380 days) revenue / net-income periods; NBIS RUB and YTD periods
are excluded (#203). Each outcome is a raw SPY-unadjusted 20/60-session return after the filing date.

For a SEC revenue-YoY evidence item the context answers: "historically, after a filing in the same
YoY bucket, how did the stock do?" — for the symbol and pooled over all symbols, with n shown.
Look-ahead guard: only filings before the research lock and outcome windows that closed on/before the
research session are counted. used_in_decision=false: the context never changes stance, sign or weight.
Fewer than MIN_N samples → status insufficient_n (shown, descriptive only).

Other outcome memories stay disconnected (see DISCONNECTED) until they have matured, clean samples.
"""
from __future__ import annotations
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "research" / "archive" / "fundamental_observations.jsonl"
OUT = ROOT / "research" / "archive" / "fundamental_outcomes.jsonl"
MEMORY = ROOT / "docs" / "research" / "company_fundamental_outcome_memory.json"  # summary of OUT; provenance only
MIN_N = 30
HORIZONS = (20, 60)
DISCONNECTED = {
    "market_state_outcome_scorecards": "only 5-session early reads matured (no 20/60-session sample), n < 30",
    "macro_outcome_memory": "0 matured outcomes on live macro observations",
    "event_outcome_memory": "matured rows are backfilled/non-live events or 5-session reads; forward-eligible matured = 0",
    "options_opportunity_outcome_memory": "0 matured 20-session outcomes",
    "support_volatility_outcome_memory": "not audited clean for research use yet",
    "gold_signal_outcomes": "owner discipline module; not research evidence",
}
_cache = {}


def _jsonl(p):
    p = Path(p)
    if not p.exists():
        return [], None
    raw = p.read_bytes()
    return [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()], hashlib.sha256(raw).hexdigest()


def bucket(yoy):
    """Same thresholds as the sec_revenue_yoy evidence sign in daily_research_job."""
    if yoy is None:
        return None
    return 1 if yoy > 0.10 else (-1 if yoy < 0 else 0)


def clean_rows(obs, outs):
    """Outcomes joined to clean observations: [(symbol, filed, yoy_bucket, horizon, horizon_end, return_pct)]."""
    keep = {}
    for o in obs:
        bad = False
        for name, m in (o.get("metrics") or {}).items():
            if m.get("unit") not in ("USD", "USD/shares", "shares", None):
                bad = True
            if name in ("revenue", "net_income") and m.get("start") and m.get("end"):
                dd = (date.fromisoformat(m["end"]) - date.fromisoformat(m["start"])).days
                if not (80 <= dd <= 100 or 330 <= dd <= 380):
                    bad = True
        rev = (o.get("metrics") or {}).get("revenue") or {}
        if not bad and rev.get("yoy_pct") is not None:
            keep[o["observation_id"]] = bucket(float(rev["yoy_pct"]) / 100.0)
    rows = []
    for x in outs:
        b = keep.get(x.get("observation_id"))
        if b is None or x.get("return_pct") is None:
            continue
        rows.append((x["symbol"], str(x.get("filed")), b, int(x["horizon_sessions"]), str(x.get("horizon_end")), float(x["return_pct"])))
    return rows


def load():
    if "rows" not in _cache:
        obs, h1 = _jsonl(OBS)
        outs, h2 = _jsonl(OUT)
        _cache["rows"] = clean_rows(obs, outs)
        try:
            mem = json.loads(MEMORY.read_text(encoding="utf-8"))
        except Exception:
            mem = {}
        _cache["meta"] = {"observations": {"source": str(OBS.relative_to(ROOT)), "sha256": h1},
                          "outcomes": {"source": str(OUT.relative_to(ROOT)), "sha256": h2,
                                       "memory_artifact": "docs/research/company_fundamental_outcome_memory.json",
                                       "memory_generated_at": mem.get("generated_at")}}
    return _cache["rows"], _cache["meta"]


def _stats(xs):
    if not xs:
        return {"n": 0, "mean_return_pct": None, "positive_rate": None}
    return {"n": len(xs), "mean_return_pct": round(sum(xs) / len(xs), 3), "positive_rate": round(sum(1 for x in xs if x > 0) / len(xs), 3)}


def context(symbol, yoy, market_as_of, lock_date, rows=None, meta=None):
    if rows is None:
        rows, meta = load()
    b = bucket(yoy)
    if b is None:
        return None
    usable = [r for r in rows if r[1] < lock_date[:10] and r[4] <= market_as_of and r[2] == b]
    out = {"used_in_decision": False, "yoy_bucket": {1: "> +10%", 0: "0 to +10%", -1: "< 0"}[b],
           "subset": "clean: USD units, quarter/annual periods (#203); raw return after filing, not benchmark-adjusted",
           "symbol": {}, "pooled": {}, "min_n": MIN_N, "inputs": meta}
    for h in HORIZONS:
        out["symbol"][str(h)] = _stats([r[5] for r in usable if r[0] == symbol and r[3] == h])
        out["pooled"][str(h)] = _stats([r[5] for r in usable if r[3] == h])
    n_sym = min(out["symbol"][str(h)]["n"] for h in HORIZONS)
    n_pool = min(out["pooled"][str(h)]["n"] for h in HORIZONS)
    out["status"] = ("descriptive_symbol_n_ge_min" if n_sym >= MIN_N else
                     "descriptive_pooled_only" if n_pool >= MIN_N else "insufficient_n")
    return out


def summary():
    rows, meta = load()
    from collections import Counter
    return {"clean_outcomes_by_horizon": dict(Counter(r[3] for r in rows)), "symbols": sorted({r[0] for r in rows}),
            "inputs": meta, "disconnected": DISCONNECTED}


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=1))
