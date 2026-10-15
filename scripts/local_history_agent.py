#!/usr/bin/env python3
"""myAlphaView V5.3 local historical store + learning engine.

Source of truth:
- data/history/stooq_watchlist.zip (user-supplied STOOQ daily OHLCV)
- docs/data.json (the dashboard's already-fetched latest completed daily bar)

Goals:
1. Never redownload years of history during Daily Dashboard Update.
2. Append only a new completed bar when docs/data.json has one.
3. Rebuild a causal Trend Pulse event study from local history.
4. Produce a compact browser-readable learning report.  This report may rank
   research attention, but it never changes production thresholds or trades.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
DASHBOARD = ROOT / "docs" / "data.json"
OUTPUT = ROOT / "docs" / "research" / "historical_journal.json"
APP_VERSION = "5.3.0"
HORIZONS = (20, 60, 120)
STATES = ("趋势启动", "二次启动", "趋势延续", "修复中", "高位钝化", "趋势退潮", "趋势恶化")
EVENT_STATES = set(STATES)
COOLDOWN = 10
LOOKBACK_YEARS = 5
WARMUP_DAYS = 420

sys.path.insert(0, str(ROOT / "scripts"))
from backtest_trend_pulse import trend_indicators, base_pulse, classify_states  # noqa: E402


def symbol_from_name(name: str) -> Optional[str]:
    m = re.match(r"^([a-z0-9.\-]+)_us_d\.csv$", Path(name).name.lower())
    return m.group(1).upper() if m else None


def read_archive() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    if not ARCHIVE.exists():
        return out
    with zipfile.ZipFile(ARCHIVE, "r") as z:
        for name in sorted(z.namelist()):
            symbol = symbol_from_name(name)
            if not symbol or name.startswith("__MACOSX/"):
                continue
            try:
                raw = z.read(name)
                df = pd.read_csv(io.BytesIO(raw))
                df.columns = [str(c).strip().lower() for c in df.columns]
                need = ["date", "open", "high", "low", "close", "volume"]
                if not all(c in df.columns for c in need):
                    continue
                df = df[need].copy()
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                for c in need[1:]:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                df = df.dropna(subset=["date", "open", "high", "low", "close"])
                df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
                df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
                out[symbol] = df
            except Exception as exc:
                print(f"WARNING history read {name}: {exc}")
    return out


def write_archive(store: Dict[str, pd.DataFrame]) -> None:
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVE.with_suffix(".tmp.zip")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for symbol, df in sorted(store.items()):
            x = df.copy().reset_index()
            x.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
            x["Date"] = pd.to_datetime(x["Date"]).dt.strftime("%Y-%m-%d")
            buf = io.StringIO()
            x.to_csv(buf, index=False, lineterminator="\n")
            z.writestr(f"{symbol.lower()}_us_d.csv", buf.getvalue())
    tmp.replace(ARCHIVE)


REGISTRY = ROOT / "research" / "audit" / "symbol_registry.json"
BASIS_TOLERANCE = 0.005  # fallback rows must match archived closes on overlapping sessions within 0.5 %


def dashboard_bar(data: dict, symbol: str) -> Optional[dict]:
    """Latest dashboard row for a symbol, exactly as published (no field is invented).

    stocks.* rows carry full OHLC; core/index rows are usually close-only. Missing open/high/low stay
    missing (D-06): a close is never copied into open/high/low.
    """
    for group in ("stocks", "core", "index"):
        row = (data.get(group) or {}).get(symbol)
        if isinstance(row, dict) and row.get("close") is not None:
            out = {k: row.get(k) for k in ("date", "open", "high", "low", "close", "volume")}
            out["source"] = f"docs/data.json {group}.{symbol}"
            return out
    return None


def collection_universe(store: Dict[str, pd.DataFrame]) -> List[str]:
    """D-05: archive symbols ∪ registry data_collection_universe (display-independent)."""
    syms = set(store)
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        syms |= set(((reg.get("universes") or {}).get("data_collection_universe")) or [])
    except Exception:
        pass
    return sorted(s for s in syms if s and s != "VIX")


FALLBACK_DIAG: dict = {}


def _yahoo_recent(symbols: List[str]) -> Dict[str, List[dict]]:
    """Free fallback (Yahoo via yfinance, already a Daily dependency): last ~10 daily bars, full OHLC only.

    P0-2 (#133 6183848571): every call records diagnostics in FALLBACK_DIAG — one batched request, the
    exception if any, and per symbol the last date Yahoo returned before and after dropping incomplete rows,
    so a missing bar can be told apart from an empty response, a rate limit or an unfinalised (NaN) row."""
    global FALLBACK_DIAG
    FALLBACK_DIAG = {"provider": "Yahoo (yfinance download, period=10d, interval=1d)", "requests": 0,
                     "requested_symbols": len(symbols), "error": None, "per_symbol": {}}
    if not symbols:
        return {}
    try:
        import yfinance as yf
        from source_history_cache import normalize_yf
        FALLBACK_DIAG["requests"] = 1
        raw = yf.download(symbols, period="10d", interval="1d", auto_adjust=False, progress=False,
                          threads=False, actions=False, group_by="column", timeout=30)
    except Exception as exc:
        print(f"WARNING fallback OHLCV fetch failed: {type(exc).__name__}")
        FALLBACK_DIAG["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return {}
    FALLBACK_DIAG["raw_empty"] = bool(raw is None or getattr(raw, "empty", True))
    out: Dict[str, List[dict]] = {}
    for sym in symbols:
        d = FALLBACK_DIAG["per_symbol"].setdefault(sym, {})
        try:
            d["raw_last_date"] = _raw_last_date(raw, sym)
            df = normalize_yf(raw, sym)
        except Exception as exc:
            d["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            continue
        d["rows"] = int(len(df))
        d["last_complete_date"] = None if df.empty else df.index.max().date().isoformat()
        out[sym] = [{"date": d.date().isoformat(), "open": r.open, "high": r.high, "low": r.low,
                     "close": r.close, "volume": r.volume} for d, r in df.iterrows()]
    return out


def _raw_last_date(raw, sym):
    """Last index date Yahoo returned for sym, including rows later dropped as incomplete (NaN OHLC)."""
    if raw is None or getattr(raw, "empty", True):
        return None
    try:
        sub = raw
        if isinstance(raw.columns, pd.MultiIndex):
            lv = -1 if sym in raw.columns.get_level_values(-1) else 0
            sub = raw.xs(sym, axis=1, level=lv, drop_level=True)
        sub = sub.dropna(how="all")
        return None if sub.empty else pd.to_datetime(sub.index.max()).date().isoformat()
    except Exception:
        return None


def _hist_dict(df: pd.DataFrame) -> dict:
    return {d.date().isoformat(): (float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume))
            for d, r in df.iterrows()}


def append_latest(store: Dict[str, pd.DataFrame], fetch_fallback=None, expected=None) -> dict:
    """Append finalized real OHLCV bars for the whole data-collection universe (D-05 / D-06).

    Rules (scripts/ohlcv_merge.py): full OHLC only; close-only rows are reported as close_only and never
    written; an existing date with different values is a quarantined conflict; missing stays missing;
    sessions after the latest completed NYSE session are not_final. Sources, in order:
      1. docs/data.json stocks/core/index (already fetched by Daily; no extra call)
      2. free fallback for symbols still without a full bar for the expected session (Yahoo, last ~10 bars),
         accepted only when its closes match the archive on overlapping sessions (same price basis).
    """
    import ohlcv_merge as om
    import trading_calendar as tcal
    expected = expected or tcal.expected_latest_completed_session().isoformat()
    fetch_fallback = _yahoo_recent if fetch_fallback is None else fetch_fallback
    result = {"expected_session": expected, "appended": [], "unchanged": [], "quarantined": [], "missing": [],
              "close_only": [], "not_final": [], "sources": {}}
    data = json.loads(DASHBOARD.read_text(encoding="utf-8")) if DASHBOARD.exists() else {}
    changed = False
    need_fallback = []
    for symbol in collection_universe(store):
        df = store.get(symbol)
        if df is None or df.empty:
            result["missing"].append(symbol)
            result["sources"][symbol] = "no canonical history (a series is never started from one bar)"
            continue
        last = df.index.max().date().isoformat()
        row = dashboard_bar(data, symbol)
        status, bar = om.normalize_bar(row, expected) if row else ("missing", "not in docs/data.json")
        if status == "ok":
            hist = _hist_dict(df.tail(5))
            if bar["date"] < last and bar["date"] not in hist:
                r, res = "unchanged", {}
            else:
                res, _ = om.merge_bar(hist, status, bar)
                r = res["result"]
            if r == "appended":
                df.loc[pd.Timestamp(bar["date"]), ["open", "high", "low", "close", "volume"]] = \
                    [bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]]
                store[symbol] = df = df.sort_index()
                result["appended"].append({"symbol": symbol, "date": bar["date"], "close": bar["close"], "source": row["source"]})
                changed = True
            elif r == "unchanged":
                result["unchanged"].append(symbol)
            else:
                result["quarantined"].append({"symbol": symbol, **{k: v for k, v in res.items() if k != "result"},
                                              "reason": r, "source": row["source"]})
            result["sources"][symbol] = row["source"]
            last = df.index.max().date().isoformat()
        elif status == "close_only":
            result["close_only"].append({"symbol": symbol, "date": bar["date"], "source": row["source"]})
        elif status == "not_final":
            result["not_final"].append({"symbol": symbol, "detail": bar})
        if last < expected:
            need_fallback.append(symbol)
    global FALLBACK_DIAG
    FALLBACK_DIAG = {}
    fetched = fetch_fallback(need_fallback) if need_fallback else {}
    diag = dict(FALLBACK_DIAG) if FALLBACK_DIAG else {"provider": "injected fetcher (test/other)", "requests": int(bool(need_fallback)),
                                                      "requested_symbols": len(need_fallback), "error": None, "per_symbol": {}}
    for sym in need_fallback:
        d = diag["per_symbol"].setdefault(sym, {})
        rows = fetched.get(sym) or []
        d.setdefault("rows", len(rows))
        d.setdefault("last_complete_date", max((r["date"] for r in rows), default=None))
    result["fallback_diagnostics"] = diag
    for symbol in need_fallback:
        df = store[symbol]
        rows = fetched.get(symbol) or []
        hist = _hist_dict(df.tail(15))
        bars = [b for st, b in (om.normalize_bar(r, expected) for r in rows) if st == "ok"]
        overlap = [b for b in bars if b["date"] in hist]
        mism = [b["date"] for b in overlap if abs(b["close"] / hist[b["date"]][3] - 1) > BASIS_TOLERANCE]
        new = sorted((b for b in bars if b["date"] > df.index.max().date().isoformat()), key=lambda b: b["date"])
        if not new:
            dd = diag["per_symbol"].get(symbol, {})
            dd["outcome"] = ("empty_response" if not rows else
                             "no_bar_after_archive (raw_last=%s, complete_last=%s)" % (dd.get("raw_last_date"), dd.get("last_complete_date")))
            result["missing"].append(symbol)
            result["sources"].setdefault(symbol, "stale: no finalized full-OHLC bar after the archive from any free source")
            continue
        if not overlap or mism:
            result["quarantined"].append({"symbol": symbol, "reason": "fallback_basis_unverified" if not overlap else "fallback_basis_mismatch",
                                          "dates": mism, "source": "Yahoo (yfinance) fallback"})
            continue
        cur = _hist_dict(df.tail(5))
        for b in new:
            res, cur = om.merge_bar(cur, "ok", b)
            if res["result"] != "appended":
                result["quarantined"].append({"symbol": symbol, "date": b["date"], "reason": res["result"], "source": "Yahoo (yfinance) fallback"})
                break
            df.loc[pd.Timestamp(b["date"]), ["open", "high", "low", "close", "volume"]] = [b["open"], b["high"], b["low"], b["close"], b["volume"]]
            result["appended"].append({"symbol": symbol, "date": b["date"], "close": b["close"], "source": "Yahoo (yfinance) fallback"})
            changed = True
        store[symbol] = df.sort_index()
        result["sources"][symbol] = "Yahoo (yfinance) fallback"
    if changed:
        write_archive(store)
    return result


def zone(score: float) -> str:
    if score >= 75: return "强势高位"
    if score >= 50: return "上升确认"
    if score >= 20: return "转强区"
    if score > -20: return "震荡区"
    if score > -60: return "弱势区"
    return "风险区"


def fwd_stats(scored: pd.DataFrame, i: int) -> dict:
    entry = float(scored["close"].iloc[i])
    out = {}
    for h in HORIZONS:
        if i + h >= len(scored):
            out[str(h)] = None
            continue
        end = float(scored["close"].iloc[i + h])
        path = scored["close"].iloc[i + 1:i + h + 1].astype(float).to_numpy()
        out[str(h)] = {
            "date": scored.index[i + h].date().isoformat(),
            "return": end / entry - 1.0,
            "mae": float(path.min() / entry - 1.0) if len(path) else None,
            "mfe": float(path.max() / entry - 1.0) if len(path) else None,
        }
    return out


def build_daily_pulse_local(df: pd.DataFrame) -> pd.DataFrame:
    """Fast causal replay. Daily components match Trend Pulse; weekly bias uses
    the prior *completed* weekly bar so historical reconstruction never sees a
    future Thu/Fri while evaluating Mon-Wed. This is intentionally conservative.
    """
    ind = trend_indicators(df)
    w = df.resample("W-FRI").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    if len(w):
        c=w["close"]
        e8=c.ewm(span=8,adjust=False).mean(); e21=c.ewm(span=21,adjust=False).mean()
        macd=c.ewm(span=6,adjust=False).mean()-c.ewm(span=13,adjust=False).mean()
        wb=pd.Series(0.0,index=w.index)
        wb += np.where((c>e8)&(e8>e21),8,np.where((c<e8)&(e8<e21),-8,0))
        wb += np.where(macd>0,7,-7)
        # Shift one weekly observation: only prior completed week is used.
        wb=wb.shift(1).fillna(0.0)
        weekly_label=pd.Series(np.where(wb>=8,"多头",np.where(wb<=-8,"空头","过渡")),index=w.index)
        map_df=pd.DataFrame({"weekly_bias":wb,"weekly":weekly_label}).reindex(ind.index,method="ffill").fillna({"weekly_bias":0.0,"weekly":"数据不足"})
    else:
        map_df=pd.DataFrame({"weekly_bias":0.0,"weekly":"数据不足"},index=ind.index)
    pulse=(base_pulse(ind)+map_df["weekly_bias"]).clip(-100,100)
    states=classify_states(pulse)
    out=ind.join(map_df).join(states);out["pulse"]=pulse
    return out


def build_events(symbol: str, df: pd.DataFrame) -> Tuple[List[dict], dict]:
    end = df.index.max()
    start = end - pd.DateOffset(years=LOOKBACK_YEARS) - pd.Timedelta(days=WARMUP_DAYS)
    work = df[df.index >= start].copy()
    if len(work) < 80:
        return [], {"symbol": symbol, "rows": len(df), "eligible": False, "reason": "history_too_short"}
    scored = build_daily_pulse_local(work)
    scored = scored.replace([np.inf, -np.inf], np.nan)
    events: List[dict] = []
    last_state_event: Dict[str, int] = defaultdict(lambda: -10_000)
    horizon_start = end - pd.DateOffset(years=LOOKBACK_YEARS)
    for i in range(1, len(scored)):
        dt = scored.index[i]
        if dt < horizon_start:
            continue
        state = str(scored["state"].iloc[i])
        prev = str(scored["state"].iloc[i - 1])
        if state not in EVENT_STATES or state == prev:
            continue
        if i - last_state_event[state] < COOLDOWN:
            continue
        score = float(scored["pulse"].iloc[i]) if pd.notna(scored["pulse"].iloc[i]) else None
        if score is None:
            continue
        event = {
            "symbol": symbol,
            "date": dt.date().isoformat(),
            "price": round(float(scored["close"].iloc[i]), 5),
            "score": round(score, 2),
            "zone": zone(score),
            "stage": state,
            "weekly": str(scored.get("weekly", pd.Series(index=scored.index, dtype=object)).iloc[i] or ""),
            "outcomes": fwd_stats(scored, i),
        }
        events.append(event)
        last_state_event[state] = i
    latest = scored.iloc[-1]
    meta = {
        "symbol": symbol,
        "rows": len(df),
        "first_date": df.index.min().date().isoformat(),
        "last_date": df.index.max().date().isoformat(),
        "eligible": len(df) >= 220,
        "latest_score": round(float(latest["pulse"]), 2) if pd.notna(latest.get("pulse")) else None,
        "latest_stage": str(latest.get("state") or ""),
    }
    return events, meta


def enrich_relative_qqq(events: List[dict], qqq: Optional[pd.DataFrame]) -> None:
    if qqq is None or qqq.empty:
        return
    close=qqq["close"].astype(float)
    for e in events:
        try:
            d0=pd.Timestamp(e["date"]); p0=float(close.loc[d0]) if d0 in close.index else None
            if not p0:
                continue
            for h in HORIZONS:
                o=e["outcomes"].get(str(h))
                if not o or not o.get("date"):
                    continue
                d1=pd.Timestamp(o["date"]); p1=float(close.loc[d1]) if d1 in close.index else None
                if p1:
                    qret=p1/p0-1.0; o["qqq_return"]=qret; o["excess_vs_qqq"]=o["return"]-qret
        except Exception:
            continue


def _mean(vals: Iterable[float]) -> Optional[float]:
    x = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
    return sum(x) / len(x) if x else None


def summarize_group(events: List[dict], stage: str, horizon: int) -> dict:
    rows = [e for e in events if e["stage"] == stage and e["outcomes"].get(str(horizon))]
    rets = [e["outcomes"][str(horizon)]["return"] for e in rows]
    maes = [e["outcomes"][str(horizon)]["mae"] for e in rows]
    mfes = [e["outcomes"][str(horizon)]["mfe"] for e in rows]
    excess = [e["outcomes"][str(horizon)].get("excess_vs_qqq") for e in rows]
    if not rets:
        return {"n": 0, "avg": None, "median": None, "positive_rate": None, "mae_avg": None, "mfe_avg": None}
    arr = np.asarray(rets, dtype=float)
    return {
        "n": int(len(arr)),
        "avg": float(arr.mean()),
        "median": float(np.median(arr)),
        "positive_rate": float((arr > 0).mean()),
        "mae_avg": _mean(maes),
        "mfe_avg": _mean(mfes),
        "excess_vs_qqq_avg": _mean(excess),
    }


def confidence_label(stage: str, s: dict) -> dict:
    n = int(s.get("n") or 0); pr = s.get("positive_rate"); avg = s.get("avg")
    if n < 20 or pr is None or avg is None:
        return {"level": "insufficient", "label": "样本不足", "research_adjustment": 0}
    bearish = stage in {"趋势退潮", "趋势恶化"}
    # This is research-priority metadata only, not a trading score.
    if bearish:
        if pr <= 0.40 and avg < 0:
            return {"level": "strong", "label": "历史风险较一致", "research_adjustment": -8}
        if pr <= 0.48:
            return {"level": "moderate", "label": "历史风险偏高", "research_adjustment": -4}
    else:
        if pr >= 0.62 and avg > 0:
            return {"level": "strong", "label": "历史表现较一致", "research_adjustment": 8}
        if pr >= 0.55 and avg > 0:
            return {"level": "moderate", "label": "历史表现偏正", "research_adjustment": 4}
    return {"level": "mixed", "label": "历史结果分化", "research_adjustment": 0}


def build_report(store: Dict[str, pd.DataFrame], update_result: dict) -> dict:
    all_events: List[dict] = []
    coverage = []
    for idx, (symbol, df) in enumerate(sorted(store.items()), 1):
        print(f"history-agent {idx}/{len(store)} {symbol}: {len(df)} rows")
        try:
            events, meta = build_events(symbol, df)
            all_events.extend(events); coverage.append(meta)
        except Exception as exc:
            coverage.append({"symbol": symbol, "rows": len(df), "eligible": False, "reason": str(exc)[:180]})
            print(f"WARNING history-agent {symbol}: {exc}")

    enrich_relative_qqq(all_events, store.get("QQQ"))

    profiles = {}
    for stage in STATES:
        hstats = {str(h): summarize_group(all_events, stage, h) for h in HORIZONS}
        conf = confidence_label(stage, hstats["60"])
        profiles[stage] = {"horizons": hstats, "evidence": conf}

    by_symbol = {}
    for symbol in sorted(store):
        ev = [e for e in all_events if e["symbol"] == symbol]
        by_symbol[symbol] = {
            "events": len(ev),
            "mature_20": sum(1 for e in ev if e["outcomes"].get("20")),
            "mature_60": sum(1 for e in ev if e["outcomes"].get("60")),
            "mature_120": sum(1 for e in ev if e["outcomes"].get("120")),
        }

    report = {
        "version": APP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "user-supplied STOOQ OHLCV + daily dashboard append",
        "method": "causal Trend Pulse state-entry event study; 5y window; 10-session same-state cooldown",
        "guardrails": [
            "Historical learning may change research priority only; it does not modify core ETF thresholds.",
            "No automatic order placement.",
            "No historical option P&L is inferred from stock returns.",
            "Samples below 20 are explicitly marked insufficient.",
        ],
        "coverage": coverage,
        "update": update_result,
        "summary": {
            "symbols": len(store),
            "events": len(all_events),
            "mature_20": sum(1 for e in all_events if e["outcomes"].get("20")),
            "mature_60": sum(1 for e in all_events if e["outcomes"].get("60")),
            "mature_120": sum(1 for e in all_events if e["outcomes"].get("120")),
        },
        "profiles": profiles,
        "by_symbol": by_symbol,
        # Recent events are enough for UI drill-down; aggregates use the full set.
        "recent_events": sorted(all_events, key=lambda e: (e["date"], e["symbol"]), reverse=True)[:600],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-update", action="store_true", help="do not append docs/data.json latest bars")
    args = p.parse_args()
    store = read_archive()
    if not store:
        print("WARNING: no local STOOQ history archive; skipping historical learning")
        return 0
    update = {"appended": [], "unchanged": [], "quarantined": [], "missing": [], "close_only": [], "not_final": []}
    if not args.no_update:
        update = append_latest(store)
        # Re-read after archive rewrite to validate persisted bytes.
        store = read_archive()
    report = build_report(store, update)
    print(json.dumps({"summary": report["summary"], "update": update}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
