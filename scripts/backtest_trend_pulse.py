#!/usr/bin/env python3
"""Walk-forward event study for myAlphaView Trend Pulse V1.

Purpose
-------
Validate whether three state transitions have useful forward-return separation:
  * 趋势启动 (trend_start)
  * 二次启动 (second_start)
  * 趋势退潮 (trend_fade)

Design choices
--------------
* 5 years of split-adjusted daily OHLCV from Yahoo Finance (yfinance).
* Strictly causal / walk-forward calculations; no future bars in any indicator.
* Weekly bias is recomputed as-of each daily close to avoid partial-week lookahead.
* Events are state *entries*, not every day spent in a state.
* A 10-trading-day same-state cooldown reduces duplicate clusters.
* Forward returns are close-to-close from the signal close over 5/10/20/60 sessions.
* Results are descriptive research, not trading instructions.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

DEFAULT_SYMBOLS = ["IREN", "NVDA", "ORCL", "TSLA"]
HORIZONS = (5, 10, 20, 60)
STATE_KEYS = {
    "趋势启动": "trend_start",
    "二次启动": "second_start",
    "趋势退潮": "trend_fade",
}


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def trend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c, h, l = out["close"], out["high"], out["low"]
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    out["ema50"] = c.ewm(span=50, adjust=False).mean()
    out["ema200"] = c.ewm(span=200, adjust=False).mean()
    out["macd"] = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    rs = _wilder(gain, 14) / _wilder(loss, 14).replace(0, np.nan)
    out["rsi"] = 100 - 100 / (1 + rs)

    prev_close = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    out["atr"] = _wilder(tr, 14)
    up_move, down_move = h.diff(), -l.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    plus_di = 100 * _wilder(plus_dm, 14) / out["atr"].replace(0, np.nan)
    minus_di = 100 * _wilder(minus_dm, 14) / out["atr"].replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out["plus_di"], out["minus_di"], out["adx"] = plus_di, minus_di, _wilder(dx, 14)

    # Same Supertrend(10,3) implementation as website V4.3.x.
    atr10 = _wilder(tr, 10)
    hl2 = (h + l) / 2
    upper, lower = hl2 + 3.0 * atr10, hl2 - 3.0 * atr10
    final_upper, final_lower = upper.copy(), lower.copy()
    st = pd.Series(index=out.index, dtype=float)
    direction = pd.Series(index=out.index, dtype=float)
    for i in range(1, len(out)):
        if pd.notna(final_upper.iloc[i - 1]):
            final_upper.iloc[i] = upper.iloc[i] if (upper.iloc[i] < final_upper.iloc[i - 1] or c.iloc[i - 1] > final_upper.iloc[i - 1]) else final_upper.iloc[i - 1]
            final_lower.iloc[i] = lower.iloc[i] if (lower.iloc[i] > final_lower.iloc[i - 1] or c.iloc[i - 1] < final_lower.iloc[i - 1]) else final_lower.iloc[i - 1]
        prev_st = st.iloc[i - 1]
        if pd.isna(prev_st):
            st.iloc[i] = final_lower.iloc[i] if c.iloc[i] >= hl2.iloc[i] else final_upper.iloc[i]
        elif prev_st == final_upper.iloc[i - 1]:
            st.iloc[i] = final_upper.iloc[i] if c.iloc[i] <= final_upper.iloc[i] else final_lower.iloc[i]
        else:
            st.iloc[i] = final_lower.iloc[i] if c.iloc[i] >= final_lower.iloc[i] else final_upper.iloc[i]
        direction.iloc[i] = 1.0 if c.iloc[i] >= st.iloc[i] else -1.0
    out["supertrend"] = st
    out["st_dir"] = direction.fillna(0)

    vol = out["volume"].fillna(0)
    obv_step = pd.Series(0.0, index=out.index)
    obv_step[delta > 0] = vol[delta > 0]
    obv_step[delta < 0] = -vol[delta < 0]
    out["obv"] = obv_step.cumsum()
    out["obv_slope10"] = out["obv"] - out["obv"].shift(10)

    tp = (h + l + c) / 3
    flow = tp * vol
    pos = flow.where(tp.diff() > 0, 0.0).rolling(14).sum()
    neg = flow.where(tp.diff() < 0, 0.0).rolling(14).sum()
    ratio = pos / neg.replace(0, np.nan)
    out["mfi"] = 100 - 100 / (1 + ratio)

    out["high20"] = h.rolling(20).max()
    out["low20"] = l.rolling(20).min()
    out["prior_high20"] = out["high20"].shift(20)
    out["prior_low20"] = out["low20"].shift(20)
    return out


def base_pulse(ind: pd.DataFrame) -> pd.Series:
    x = ind
    score = pd.Series(0.0, index=x.index)
    bull_stack = (x.close > x.ema20) & (x.ema20 > x.ema50)
    bear_stack = (x.close < x.ema20) & (x.ema20 < x.ema50)
    score += bull_stack.astype(float) * 20 - bear_stack.astype(float) * 20
    score += ((~bull_stack) & (x.close > x.ema20)).astype(float) * 8
    score -= ((~bear_stack) & (x.close < x.ema20)).astype(float) * 8
    score += x.st_dir.fillna(0) * 20
    adx_weight = ((x.adx.fillna(0) - 15) / 20).clip(0, 1) * 15
    score += adx_weight.where(x.plus_di >= x.minus_di, -adx_weight)
    score += (x.macd_hist > 0).astype(float) * 10 - (x.macd_hist < 0).astype(float) * 10
    score += ((x.rsi.fillna(50) - 50) / 20).clip(-1, 1) * 10
    hh, hl = x.high20 > x.prior_high20, x.low20 > x.prior_low20
    lh, ll = x.high20 < x.prior_high20, x.low20 < x.prior_low20
    score += (hh & hl).astype(float) * 10 - (lh & ll).astype(float) * 10
    score += (x.obv_slope10 > 0).astype(float) * 5 - (x.obv_slope10 < 0).astype(float) * 5
    return score


def weekly_bias_asof(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute weekly trend using only bars available through each date."""
    bias_vals, labels = [], []
    for i in range(len(df)):
        sub = df.iloc[: i + 1]
        if len(sub) < 80:
            bias_vals.append(0.0); labels.append("数据不足"); continue
        w = sub.resample("W-FRI").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
        if len(w) < 16:
            bias_vals.append(0.0); labels.append("数据不足"); continue
        c = w.close
        e8 = c.ewm(span=8, adjust=False).mean()
        e21 = c.ewm(span=21, adjust=False).mean()
        macd = c.ewm(span=6, adjust=False).mean() - c.ewm(span=13, adjust=False).mean()
        bias = 0.0
        bias += 8 if c.iloc[-1] > e8.iloc[-1] > e21.iloc[-1] else (-8 if c.iloc[-1] < e8.iloc[-1] < e21.iloc[-1] else 0)
        bias += 7 if macd.iloc[-1] > 0 else -7
        bias_vals.append(bias)
        labels.append("多头" if bias >= 8 else ("空头" if bias <= -8 else "过渡"))
    return pd.DataFrame({"weekly_bias": bias_vals, "weekly": labels}, index=df.index)


def classify_states(pulse: pd.Series) -> pd.DataFrame:
    state, slope5s, slope20s = [], [], []
    vals = pulse.values
    for i, cur in enumerate(vals):
        if not np.isfinite(cur):
            state.append("不可用"); slope5s.append(np.nan); slope20s.append(np.nan); continue
        prev = vals[i - 1] if i >= 1 and np.isfinite(vals[i - 1]) else cur
        slope5 = cur - vals[i - 5] if i >= 5 and np.isfinite(vals[i - 5]) else 0.0
        slope20 = cur - vals[i - 20] if i >= 20 and np.isfinite(vals[i - 20]) else slope5
        recent = vals[max(0, i - 11): i + 1]
        finite_recent = recent[np.isfinite(recent)]
        rebound = bool(len(finite_recent) >= 6 and cur > 30 and slope5 > 6 and finite_recent.min() < cur - 12)
        crossed = bool(prev <= 0 < cur and slope5 > 3)
        if cur < 0:
            s = "修复中" if slope5 > 2 else "趋势恶化"
        elif crossed:
            s = "趋势启动"
        elif cur >= 70 and slope5 < -6:
            s = "趋势退潮"
        elif cur >= 70 and abs(slope5) <= 4:
            s = "高位钝化"
        elif rebound:
            s = "二次启动"
        elif cur >= 20 and slope5 > 0:
            s = "趋势延续"
        else:
            s = "震荡观察"
        state.append(s); slope5s.append(slope5); slope20s.append(slope20)
    return pd.DataFrame({"state": state, "slope5": slope5s, "slope20": slope20s}, index=pulse.index)


def normalize_yf(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance can return either (field,ticker) or (ticker,field)
        if symbol in df.columns.get_level_values(-1):
            df = df.xs(symbol, axis=1, level=-1)
        elif symbol in df.columns.get_level_values(0):
            df = df.xs(symbol, axis=1, level=0)
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    need = ["open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in need):
        raise ValueError(f"{symbol}: Yahoo columns missing {set(need)-set(df.columns)}")
    df = df[need].copy().dropna(subset=["open","high","low","close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index().drop_duplicates()
    return df


def build_daily_pulse(df: pd.DataFrame) -> pd.DataFrame:
    ind = trend_indicators(df)
    wk = weekly_bias_asof(df)
    pulse = (base_pulse(ind) + wk["weekly_bias"]).clip(-100, 100)
    states = classify_states(pulse)
    out = ind.join(wk).join(states)
    out["pulse"] = pulse
    return out


def event_rows(symbol: str, scored: pd.DataFrame, cooldown: int = 10) -> List[dict]:
    events: List[dict] = []
    last_event_idx: Dict[str, int] = {}
    closes = scored["close"].values
    states = scored["state"].values
    for i in range(1, len(scored)):
        s = states[i]
        if s not in STATE_KEYS or s == states[i - 1]:
            continue
        key = STATE_KEYS[s]
        if i - last_event_idx.get(key, -10_000) < cooldown:
            continue
        row = {
            "symbol": symbol,
            "date": scored.index[i].date().isoformat(),
            "state": s,
            "state_key": key,
            "pulse": round(float(scored["pulse"].iloc[i]), 3),
            "slope5": round(float(scored["slope5"].iloc[i]), 3),
            "weekly": str(scored["weekly"].iloc[i]),
            "close": round(float(closes[i]), 4),
        }
        complete = False
        for h in HORIZONS:
            if i + h < len(scored):
                ret = closes[i + h] / closes[i] - 1.0
                row[f"ret_{h}d"] = float(ret)
                complete = True
            else:
                row[f"ret_{h}d"] = None
        if complete:
            events.append(row)
            last_event_idx[key] = i
    return events


def eligible_baseline(scored: pd.DataFrame) -> Dict[int, np.ndarray]:
    c = scored["close"].values
    out = {}
    # start only after enough history for stable daily + weekly components
    start = min(len(scored), 220)
    for h in HORIZONS:
        vals = [(c[i + h] / c[i] - 1.0) for i in range(start, len(c) - h) if c[i] > 0]
        out[h] = np.asarray(vals, dtype=float)
    return out


def _ci95(values: np.ndarray, seed: int = 20260926) -> Tuple[float | None, float | None]:
    values = values[np.isfinite(values)]
    if len(values) < 5:
        return None, None
    rng = np.random.default_rng(seed)
    means = np.empty(3000)
    for i in range(len(means)):
        means[i] = rng.choice(values, size=len(values), replace=True).mean()
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def summarize(events: List[dict], baselines: Dict[str, Dict[int, np.ndarray]]) -> List[dict]:
    rows = []
    for symbol in sorted(set(e["symbol"] for e in events)):
        for state_key in ("trend_start", "second_start", "trend_fade"):
            subset = [e for e in events if e["symbol"] == symbol and e["state_key"] == state_key]
            for h in HORIZONS:
                vals = np.asarray([e[f"ret_{h}d"] for e in subset if e.get(f"ret_{h}d") is not None], dtype=float)
                if len(vals) == 0:
                    continue
                base = baselines[symbol][h]
                lo, hi = _ci95(vals)
                intended_positive = state_key != "trend_fade"
                hit = float((vals > 0).mean()) if intended_positive else float((vals < 0).mean())
                base_hit = float((base > 0).mean()) if intended_positive else float((base < 0).mean())
                rows.append({
                    "symbol": symbol,
                    "state_key": state_key,
                    "state": {v:k for k,v in STATE_KEYS.items()}[state_key],
                    "horizon": h,
                    "n": int(len(vals)),
                    "mean": float(vals.mean()),
                    "median": float(np.median(vals)),
                    "directional_hit_rate": hit,
                    "baseline_mean": float(base.mean()) if len(base) else None,
                    "baseline_directional_hit_rate": base_hit if len(base) else None,
                    "mean_excess_vs_all_days": float(vals.mean() - base.mean()) if len(base) else None,
                    "worst": float(vals.min()),
                    "best": float(vals.max()),
                    "mean_ci95_lo": lo,
                    "mean_ci95_hi": hi,
                })
    # combined portfolio-level event set across all symbols
    for state_key in ("trend_start", "second_start", "trend_fade"):
        subset = [e for e in events if e["state_key"] == state_key]
        for h in HORIZONS:
            vals = np.asarray([e[f"ret_{h}d"] for e in subset if e.get(f"ret_{h}d") is not None], dtype=float)
            if len(vals) == 0:
                continue
            base = np.concatenate([baselines[s][h] for s in baselines if len(baselines[s][h])])
            lo, hi = _ci95(vals)
            intended_positive = state_key != "trend_fade"
            hit = float((vals > 0).mean()) if intended_positive else float((vals < 0).mean())
            base_hit = float((base > 0).mean()) if intended_positive else float((base < 0).mean())
            rows.append({
                "symbol": "ALL",
                "state_key": state_key,
                "state": {v:k for k,v in STATE_KEYS.items()}[state_key],
                "horizon": h,
                "n": int(len(vals)),
                "mean": float(vals.mean()),
                "median": float(np.median(vals)),
                "directional_hit_rate": hit,
                "baseline_mean": float(base.mean()),
                "baseline_directional_hit_rate": base_hit,
                "mean_excess_vs_all_days": float(vals.mean() - base.mean()),
                "worst": float(vals.min()),
                "best": float(vals.max()),
                "mean_ci95_lo": lo,
                "mean_ci95_hi": hi,
            })
    return rows


def pct(v):
    return "—" if v is None or not math.isfinite(v) else f"{v*100:.2f}%"


def build_markdown(meta: dict, summary_rows: List[dict], events: List[dict]) -> str:
    lines = [
        "# Trend Pulse V1 · 5年事件研究",
        "",
        f"生成时间：{meta['generated_at']}",
        f"数据源：{meta['data_source']}",
        f"标的：{', '.join(meta['symbols'])}",
        "",
        "## 方法",
        "- 使用拆股/分红调整后的日线OHLCV；每个交易日只使用当日及之前的数据。",
        "- 周线趋势逐日重算，避免把本周尚未发生的后续交易日带入历史信号。",
        "- 只统计状态首次进入事件，并对同类事件设置10个交易日冷却期。",
        "- 收益为信号日收盘到未来第5/10/20/60个交易日收盘的实际价格变化。",
        "- `趋势启动/二次启动` 的方向命中定义为未来收益>0；`趋势退潮`定义为未来收益<0。",
        "- Baseline 是同一股票所有可用历史交易日的同期前瞻收益，用于判断信号是否真正提供额外区分度。",
        "",
        "## 汇总",
        "|标的|状态|周期|样本N|平均收益|中位数|方向命中率|基准平均|超额|95%均值CI|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    order = {"trend_start":0,"second_start":1,"trend_fade":2}
    for r in sorted(summary_rows, key=lambda x:(x["symbol"]!="ALL", x["symbol"], order[x["state_key"]], x["horizon"])):
        ci = "—" if r["mean_ci95_lo"] is None else f"{pct(r['mean_ci95_lo'])} ~ {pct(r['mean_ci95_hi'])}"
        lines.append(f"|{r['symbol']}|{r['state']}|{r['horizon']}D|{r['n']}|{pct(r['mean'])}|{pct(r['median'])}|{pct(r['directional_hit_rate'])}|{pct(r['baseline_mean'])}|{pct(r['mean_excess_vs_all_days'])}|{ci}|")
    lines += ["", "## 解释原则", "- 样本数很少（尤其 N<8）时，不把较高平均收益视为已验证优势。", "- 95%区间跨过0，不代表信号无价值，但说明当前证据不足以确认稳定的平均方向。", "- 个股事件可能集中在特定牛熊阶段；下一步应做分年份和walk-forward分段验证。", ""]
    return "\n".join(lines)


def _previous_coverage(outdir: Path) -> dict:
    """Read the last committed coverage map, if available.

    This lets scheduled runs avoid rewriting research files on weekends/market
    holidays when Yahoo has no new completed daily bar.
    """
    path = outdir / "trend_pulse_backtest.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return (payload.get("meta") or {}).get("coverage") or {}
    except Exception as exc:
        print(f"[BACKTEST] previous coverage unreadable; full rebuild: {exc}")
        return {}


def _coverage_end_map(coverage: dict) -> dict:
    return {str(k): (v or {}).get("end") for k, v in coverage.items()}


def main():
    import yfinance as yf
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--period", default="5y")
    ap.add_argument("--outdir", default="docs/research")
    ap.add_argument(
        "--skip-if-no-new-data",
        action="store_true",
        help="Do not rewrite outputs when every symbol has the same latest completed daily bar as the previous report.",
    )
    args = ap.parse_args()

    symbols = [s.upper() for s in args.symbols]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    previous_coverage = _previous_coverage(outdir) if args.skip_if_no_new_data else {}
    all_events, baselines = [], {}
    coverage = {}

    for sym in symbols:
        print(f"[BACKTEST] download {sym} {args.period}")
        raw = yf.download(sym, period=args.period, interval="1d", auto_adjust=True, progress=False, threads=False)
        df = normalize_yf(raw, sym)
        if len(df) < 100:
            raise RuntimeError(f"{sym}: history too short ({len(df)} rows)")
        scored = build_daily_pulse(df)
        ev = event_rows(sym, scored)
        all_events.extend(ev)
        baselines[sym] = eligible_baseline(scored)
        coverage[sym] = {"rows": len(df), "start": df.index.min().date().isoformat(), "end": df.index.max().date().isoformat(), "events": len(ev)}
        print(f"[BACKTEST] {sym}: rows={len(df)}, events={len(ev)}, {coverage[sym]['start']} -> {coverage[sym]['end']}")

    if args.skip_if_no_new_data and previous_coverage:
        prev_ends = _coverage_end_map(previous_coverage)
        current_ends = _coverage_end_map(coverage)
        comparable = all(sym in prev_ends for sym in symbols)
        unchanged = comparable and all(prev_ends.get(sym) == current_ends.get(sym) for sym in symbols)
        if unchanged:
            print(f"[BACKTEST] no new completed daily bars ({current_ends}); keep existing research outputs unchanged")
            return

    summary_rows = summarize(all_events, baselines)
    now = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    meta = {
        "version":"Trend Pulse V1 / backtest-1.0",
        "generated_at":now,
        "symbols":symbols,
        "period":args.period,
        "horizons":list(HORIZONS),
        "data_source":"Yahoo Finance via yfinance, auto_adjust=True",
        "coverage":coverage,
        "lookahead_control":"weekly bias recomputed as-of each daily close",
        "event_definition":"state entry + 10 trading-day same-state cooldown",
    }

    pd.DataFrame(all_events).to_csv(outdir / "trend_pulse_events.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(outdir / "trend_pulse_summary.csv", index=False)
    with open(outdir / "trend_pulse_backtest.json", "w", encoding="utf-8") as f:
        json.dump({"meta":meta,"summary":summary_rows,"events":all_events}, f, ensure_ascii=False, indent=2)
    with open(outdir / "trend_pulse_backtest.md", "w", encoding="utf-8") as f:
        f.write(build_markdown(meta, summary_rows, all_events))
    print(f"[BACKTEST] wrote {outdir}/trend_pulse_backtest.*")


if __name__ == "__main__":
    main()
