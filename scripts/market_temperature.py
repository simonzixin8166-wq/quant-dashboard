#!/usr/bin/env python3
"""MyAlpha 市场温度 (owner decision #133 2026-10-17): one 0–100 reading of today's market risk appetite,
built only from data the pipeline already has. MyAlpha's own descriptive measure — NOT the CNN Fear & Greed
index (that stays a link-out per SENT-01) and NOT a forecast. Every reading is appended to a dated history so
its forward usefulness can be tested later; until then it is descriptive only (validated=false).

Components (each 0–100, higher = more risk appetite; missing input → unavailable, never imputed):
  momentum    SPY close vs its 125-session average            50 + 500·(close/ma125 − 1)
  strength    net 52-week new highs (S&P 500 share)            50 + 500·(nh − nl)
  breadth     share of S&P 500 members above their 50-day MA   100·b50
  volatility  VIX vs its 50-session average                     50 − 250·(vix/ma50 − 1)
  safe_haven  SPY minus TLT 20-session return                   50 + 500·(spy20 − tlt20)
  credit      High-yield OAS 20-day change (FRED)               50 − 100·Δ20 (percentage points)
Composite = mean of available components; published only when ≥ 4 of 6 are available.
"""
from __future__ import annotations
import io, json, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
BREADTH = ROOT / "docs" / "research" / "breadth_intelligence.json"
CROSS = ROOT / "docs" / "research" / "cross_asset_divergence.json"
OUT = ROOT / "docs" / "research" / "market_temperature.json"
HIST = ROOT / "docs" / "research" / "market_temperature_history.json"
MIN_COMPONENTS = 4
BANDS = ((25, "极度恐惧"), (45, "恐惧"), (56, "中性"), (76, "贪婪"), (101, "极度贪婪"))
NAMES = {"momentum": "价格动量", "strength": "股价强度", "breadth": "市场宽度",
         "volatility": "波动率", "safe_haven": "避险需求", "credit": "信用风险"}


def clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def label(score):
    if score is None:
        return "不可用"
    for hi, name in BANDS:
        if score < hi:
            return name
    return BANDS[-1][1]


def closes(zbytes: bytes, symbol: str):
    """[(date, close)] ascending from the canonical archive; [] when absent."""
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    name = next((n for n in z.namelist() if n.lower().endswith(f"/{symbol.lower()}_us_d.csv") or n.lower() == f"{symbol.lower()}_us_d.csv"), None)
    if not name:
        return []
    rows = z.read(name).decode().strip().splitlines()[1:]
    out = []
    for r in rows:
        p = r.split(",")
        try:
            out.append((p[0], float(p[4])))
        except (IndexError, ValueError):
            continue
    return sorted(out)


def ret(series, n):
    return series[-1][1] / series[-1 - n][1] - 1 if len(series) > n and series[-1 - n][1] else None


def avg_ratio(series, n):
    if len(series) < n:
        return None
    m = sum(c for _, c in series[-n:]) / n
    return series[-1][1] / m if m else None


def comp(key, score, value, as_of, source, unavailable_reason=None):
    if score is None:
        return {"key": key, "name": NAMES[key], "status": "unavailable", "reason": unavailable_reason or "input missing",
                "source": source}
    return {"key": key, "name": NAMES[key], "status": "ok", "score": round(clamp(score), 1), "value": value,
            "as_of": as_of, "source": source}


def build(zbytes: bytes, breadth: dict, cross: dict) -> dict:
    spy, vix, tlt = closes(zbytes, "spy"), closes(zbytes, "vix"), closes(zbytes, "tlt")
    m = (breadth or {}).get("metrics") or {}
    b_asof = (breadth or {}).get("as_of")
    sig = {s.get("key"): s for s in (cross or {}).get("signals") or [] if isinstance(s, dict)}
    comps = []

    r = avg_ratio(spy, 125)
    comps.append(comp("momentum", None if r is None else 50 + 500 * (r - 1), None if r is None else round(r - 1, 4),
                      spy[-1][0] if spy else None, "archive SPY close vs 125-session average", "SPY history < 125 sessions"))

    nh, nl = m.get("new_high_52w_pct"), m.get("new_low_52w_pct")
    if isinstance(nh, (int, float)) and isinstance(nl, (int, float)):
        s = 50 + 500 * (nh - nl)
        comps.append(comp("strength", s, {"new_high": round(nh, 4), "new_low": round(nl, 4)}, b_asof, "breadth_intelligence (S&P 500)"))
    else:
        comps.append(comp("strength", None, None, None, "breadth_intelligence (S&P 500)", "new-high/low share missing"))

    b50 = m.get("b50")
    comps.append(comp("breadth", None if not isinstance(b50, (int, float)) else 100 * b50,
                      None if not isinstance(b50, (int, float)) else round(b50, 4), b_asof,
                      "breadth_intelligence (S&P 500 above 50-day MA)", "50-day breadth missing"))

    v = avg_ratio(vix, 50)
    comps.append(comp("volatility", None if v is None else 50 - 250 * (v - 1),
                      None if v is None else {"vix": round(vix[-1][1], 2), "vs_ma50": round(v - 1, 4)},
                      vix[-1][0] if vix else None, "archive VIX vs 50-session average", "VIX history < 50 sessions"))

    s20, t20 = ret(spy, 20), ret(tlt, 20)
    same_day = bool(spy and tlt and spy[-1][0] == tlt[-1][0])
    sh = None if (s20 is None or t20 is None or not same_day) else 50 + 500 * (s20 - t20)
    comps.append(comp("safe_haven", sh, None if sh is None else round(s20 - t20, 4), spy[-1][0] if sh is not None else None,
                      "archive SPY vs TLT 20-session return", "SPY/TLT history missing or dates differ"))

    cw = (sig.get("credit_widening") or {}).get("value") or {}
    chg = cw.get("chg20")
    comps.append(comp("credit", None if not isinstance(chg, (int, float)) else 50 - 100 * chg,
                      None if not isinstance(chg, (int, float)) else {"hy_oas": cw.get("latest"), "chg20_pp": round(chg, 3)},
                      cw.get("date"), "FRED ICE BofA US High Yield OAS (via cross_asset_divergence)", "HY OAS missing"))

    ok = [c for c in comps if c["status"] == "ok"]
    score = round(sum(c["score"] for c in ok) / len(ok), 1) if len(ok) >= MIN_COMPONENTS else None
    dates = sorted(d for d in (c.get("as_of") for c in ok) if d)
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": dates[-1] if dates else None,
        "score": score, "label": label(score),
        "components_available": len(ok), "components_total": len(comps), "components": comps,
        "status": "ok" if score is not None else "unavailable",
        "validated": False,
        "note": "MyAlpha 自建的描述性指标，不是 CNN 恐惧与贪婪指数，也不是预测；积累历史后再检验其对 20/60 日走势的参考价值。",
        "cnn_link": "https://www.cnn.com/markets/fear-and-greed",
        "decision": "#133 2026-10-17 owner-approved; SENT-01 CNN stays link-out only",
    }


def append_history(hist: list, out: dict) -> list:
    """One row per as_of date (a re-run on the same date replaces that day's row); never rewrites other days."""
    if out.get("score") is None or not out.get("as_of"):
        return hist
    row = {"as_of": out["as_of"], "score": out["score"], "label": out["label"], "available": out["components_available"],
           "components": {c["key"]: c.get("score") for c in out["components"]}}
    keep = [h for h in hist if h.get("as_of") != out["as_of"]]
    return sorted(keep + [row], key=lambda h: h["as_of"])


def with_change(out: dict, hist: list) -> dict:
    prev = [h for h in hist if h.get("as_of") and out.get("as_of") and h["as_of"] < out["as_of"]]
    if out.get("score") is not None and prev:
        p = prev[-min(5, len(prev))]
        out["change_vs"] = {"as_of": p["as_of"], "delta": round(out["score"] - p["score"], 1)}
    return out


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def main():
    if not ARCHIVE.exists():
        print("market temperature: archive missing → unavailable")
        zbytes = None
    else:
        zbytes = ARCHIVE.read_bytes()
    out = build(zbytes, load(BREADTH, {}), load(CROSS, {})) if zbytes else build(_empty_zip(), load(BREADTH, {}), load(CROSS, {}))
    hist = load(HIST, {}).get("rows", []) if isinstance(load(HIST, {}), dict) else []
    out = with_change(out, hist)
    hist = append_history(hist, out)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    HIST.write_text(json.dumps({"version": 1, "rows": hist}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"score": out["score"], "label": out["label"], "available": out["components_available"], "as_of": out["as_of"]}, ensure_ascii=False))


def _empty_zip() -> bytes:
    b = io.BytesIO()
    zipfile.ZipFile(b, "w").close()
    return b.getvalue()


if __name__ == "__main__":
    main()
