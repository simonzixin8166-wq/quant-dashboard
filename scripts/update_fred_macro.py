#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

try:
    from fred_client import clean_value, series_observations, series_vintage_dates
except ModuleNotFoundError:
    from scripts.fred_client import clean_value, series_observations, series_vintage_dates

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "research" / "macro_context.json"
VERSION = "5.4.0"

SERIES = {
    "DFF": ("policy_rate", "Fed Funds Effective Rate"),
    "DGS2": ("yield_2y", "2Y Treasury"),
    "DGS10": ("yield_10y", "10Y Treasury"),
    "T10Y2Y": ("yield_curve_10y2y", "10Y-2Y Curve"),
    "DFII10": ("real_yield_10y", "10Y TIPS Real Yield"),
    "CPIAUCSL": ("cpi", "CPI"),
    "CPILFESL": ("core_cpi", "Core CPI"),
    "PCEPI": ("pce", "PCE Price Index"),
    "PCEPILFE": ("core_pce", "Core PCE"),
    "UNRATE": ("unemployment", "Unemployment Rate"),
    "PAYEMS": ("payrolls", "Nonfarm Payrolls"),
    "NFCI": ("financial_conditions", "Chicago Fed NFCI"),
    "BAMLH0A0HYM2": ("hy_spread", "US High Yield OAS"),
    "DTWEXBGS": ("broad_dollar", "Broad Dollar Index"),
    "VIXCLS": ("vix", "VIX"),
}


def _series_rows(series_id: str, years: int = 6) -> List[dict]:
    start = (date.today() - timedelta(days=366 * years)).isoformat()
    rows = series_observations(series_id, observation_start=start)
    output = []
    for row in rows:
        value = clean_value(row.get("value"))
        if value is None:
            continue
        output.append(
            {
                "date": row.get("date"),
                "value": value,
                "realtime_start": row.get("realtime_start"),
                "realtime_end": row.get("realtime_end"),
            }
        )
    return output


def _latest(rows):
    return rows[-1] if rows else None


def _lag(rows, n):
    return rows[-1 - n] if len(rows) > n else None


def _delta(rows, n):
    latest = _latest(rows)
    previous = _lag(rows, n)
    return latest["value"] - previous["value"] if latest and previous else None


def _yoy(rows):
    if len(rows) < 13:
        return None
    current = rows[-1]
    year, month = map(int, current["date"][:7].split("-"))
    prior_prefix = f"{year - 1:04d}-{month:02d}"
    prior = next(
        (row["value"] for row in reversed(rows[:-1]) if str(row["date"]).startswith(prior_prefix)),
        None,
    )
    return current["value"] / prior - 1.0 if prior not in (None, 0) else None


def _state_change(delta, threshold=0.25):
    if delta is None:
        return "UNKNOWN"
    if delta >= threshold:
        return "RISING"
    if delta <= -threshold:
        return "FALLING"
    return "STABLE"


def build_regime(series: Dict[str, dict]) -> dict:
    def value(key):
        return ((series.get(key) or {}).get("latest") or {}).get("value")

    def change(key, horizon="20"):
        return ((series.get(key) or {}).get("changes") or {}).get(horizon)

    curve = value("T10Y2Y")
    high_yield = value("BAMLH0A0HYM2")
    nfci = value("NFCI")
    real_yield = value("DFII10")
    policy_rate = value("DFF")
    unemployment = value("UNRATE")
    cpi = (series.get("CPIAUCSL") or {}).get("yoy")
    core_cpi = (series.get("CPILFESL") or {}).get("yoy")

    yield_curve = (
        "UNKNOWN"
        if curve is None
        else ("INVERTED" if curve < 0 else ("NORMALIZING" if curve < 0.35 else "NORMAL"))
    )
    credit = (
        "UNKNOWN"
        if high_yield is None
        else ("STRESSED" if high_yield >= 5 else ("NEUTRAL" if high_yield >= 3.5 else "EASY"))
    )
    financial = (
        "UNKNOWN"
        if nfci is None
        else ("TIGHT" if nfci >= 0.5 else ("LOOSE" if nfci <= -0.5 else "NEUTRAL"))
    )

    inflation_values = [x for x in (cpi, core_cpi) if x is not None]
    inflation_peak = max(inflation_values) if inflation_values else None
    inflation = "UNKNOWN"
    if inflation_peak is not None:
        inflation = "HOT" if inflation_peak >= 0.035 else ("COOL" if inflation_peak < 0.025 else "STABLE")

    components = []

    def risk(name, score, maximum, reason):
        components.append({"name": name, "score": score, "max": maximum, "reason": reason})

    risk(
        "policy_rate",
        15 if policy_rate is not None and policy_rate >= 5 else 8 if policy_rate is not None and policy_rate >= 4 else 2,
        15,
        f"DFF={policy_rate}",
    )
    risk(
        "yield_curve",
        15 if curve is not None and curve < -0.5 else 8 if curve is not None and curve < 0 else 2,
        15,
        f"T10Y2Y={curve}",
    )
    risk(
        "real_yield",
        15 if real_yield is not None and real_yield >= 2.5 else 8 if real_yield is not None and real_yield >= 1.5 else 3,
        15,
        f"DFII10={real_yield}",
    )
    risk(
        "inflation",
        15 if inflation_peak is not None and inflation_peak >= 0.04 else 8 if inflation_peak is not None and inflation_peak >= 0.03 else 3,
        15,
        f"inflation={inflation_peak}",
    )
    risk(
        "unemployment",
        12
        if unemployment is not None
        and change("UNRATE", "3") is not None
        and change("UNRATE", "3") >= 0.4
        else 4,
        15,
        f"UNRATE={unemployment}",
    )
    risk(
        "credit",
        15 if high_yield is not None and high_yield >= 5 else 8 if high_yield is not None and high_yield >= 3.5 else 2,
        15,
        f"HY_OAS={high_yield}",
    )
    risk(
        "financial_conditions",
        10 if nfci is not None and nfci >= 0.5 else 5 if nfci is not None and nfci >= 0 else 1,
        10,
        f"NFCI={nfci}",
    )

    score = round(sum(item["score"] for item in components) / sum(item["max"] for item in components) * 100, 1)

    return {
        "rates_regime": _state_change(change("DGS10")),
        "real_yield_regime": _state_change(change("DFII10")),
        "yield_curve": yield_curve,
        "inflation_regime": inflation,
        "credit_regime": credit,
        "financial_conditions": financial,
        "macro_risk_score": score,
        "components": components,
    }


def _load_previous() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_macro_context() -> dict:
    previous = _load_previous()
    previous_series = previous.get("series") or {}
    series = {}
    errors = []

    for series_id, (key, label) in SERIES.items():
        try:
            rows = _series_rows(series_id)
            latest = _latest(rows)
            vintages = series_vintage_dates(
                series_id,
                realtime_start=(date.today() - timedelta(days=40)).isoformat(),
            )[-8:]
            series[series_id] = {
                "key": key,
                "label": label,
                "latest": latest,
                "changes": {
                    "3": _delta(rows, 3),
                    "20": _delta(rows, 20),
                    "60": _delta(rows, 60),
                },
                "yoy": _yoy(rows) if series_id in {"CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"} else None,
                "recent_vintage_dates": vintages,
                "source": "FRED/ALFRED",
                "official": True,
            }
        except Exception as exc:
            cached = previous_series.get(series_id)
            if isinstance(cached, dict) and cached.get("latest"):
                series[series_id] = {
                    **cached,
                    "cached": True,
                    "cache_reason": str(exc)[:180],
                    "source": cached.get("source") or "FRED/ALFRED",
                }
            errors.append({"series": series_id, "error": str(exc)[:180], "cache_used": bool(cached)})

    regime = build_regime(series)
    available = sum(1 for row in series.values() if row.get("latest"))
    cached_count = sum(1 for row in series.values() if row.get("cached"))
    latest_dates = [
        str((row.get("latest") or {}).get("date"))
        for row in series.values()
        if (row.get("latest") or {}).get("date")
    ]
    newest_observation = max(latest_dates) if latest_dates else None

    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": date.today().isoformat(),
        "source": "FRED/ALFRED API",
        "point_in_time_capable": True,
        "series": series,
        "regime": regime,
        "quality": {
            "available_series": available,
            "expected_series": len(SERIES),
            "coverage": round(available / len(SERIES), 3),
            "cached_series": cached_count,
            "newest_observation": newest_observation,
            "errors": errors,
            "confidence": (
                "HIGH"
                if available >= 12 and cached_count <= 2
                else "MEDIUM"
                if available >= 8
                else "LOW"
            ),
        },
        "guardrails": [
            "Current snapshot uses information available at run time.",
            "Historical replay must query realtime_start=realtime_end=historical date.",
            "On transient FRED failures, the last valid cached series is retained and marked cached.",
            "Macro state changes research context only; it never modifies core trading thresholds.",
        ],
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = build_macro_context()
    OUT.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "macro_risk_score": fresh["regime"]["macro_risk_score"],
                "quality": fresh["quality"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
