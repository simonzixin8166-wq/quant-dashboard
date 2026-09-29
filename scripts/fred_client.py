#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.parse, urllib.request
from typing import Any, Dict, Iterable, List, Optional

BASE = "https://api.stlouisfed.org/fred"


class FredError(RuntimeError):
    pass


def _key(api_key: Optional[str] = None) -> str:
    key = api_key or os.environ.get("FRED_API_KEY", "")
    if not key:
        raise FredError("FRED_API_KEY is not configured")
    return key


def _get(endpoint: str, params: Dict[str, Any], api_key: Optional[str] = None, timeout: int = 30) -> dict:
    query = {k: v for k, v in params.items() if v is not None}
    query["api_key"] = _key(api_key)
    query["file_type"] = "json"
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "myAlphaView/5.4 learning-engine"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise FredError(f"{endpoint} request failed: {exc}") from exc


def series_observations(
    series_id: str,
    *,
    observation_start: Optional[str] = None,
    observation_end: Optional[str] = None,
    realtime_start: Optional[str] = None,
    realtime_end: Optional[str] = None,
    vintage_dates: Optional[Iterable[str]] = None,
    api_key: Optional[str] = None,
) -> List[dict]:
    payload = _get(
        "series/observations",
        {
            "series_id": series_id,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "realtime_start": realtime_start,
            "realtime_end": realtime_end,
            "vintage_dates": ",".join(vintage_dates) if vintage_dates else None,
            "limit": 100000,
        },
        api_key=api_key,
    )
    return payload.get("observations") or []


def series_vintage_dates(
    series_id: str,
    *,
    realtime_start: Optional[str] = None,
    realtime_end: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[str]:
    payload = _get(
        "series/vintagedates",
        {
            "series_id": series_id,
            "realtime_start": realtime_start,
            "realtime_end": realtime_end,
            "limit": 1000,
        },
        api_key=api_key,
    )
    return payload.get("vintage_dates") or []


def clean_value(value: Any) -> Optional[float]:
    try:
        result = float(value)
        return result if result == result else None
    except Exception:
        return None


def latest_valid(rows: Iterable[dict]) -> Optional[dict]:
    valid = []
    for row in rows:
        value = clean_value(row.get("value"))
        if value is not None:
            valid.append({**row, "value": value})
    return valid[-1] if valid else None


def observation_as_of(
    series_id: str,
    as_of: str,
    *,
    observation_start: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """Return the latest observation that was actually knowable on as_of.

    FRED/ALFRED real-time periods prevent later revisions from leaking into
    historical Situation replay.
    """
    rows = series_observations(
        series_id,
        observation_start=observation_start,
        observation_end=as_of,
        realtime_start=as_of,
        realtime_end=as_of,
        api_key=api_key,
    )
    row = latest_valid(rows)
    if row:
        row = {**row, "known_at": as_of, "series_id": series_id, "point_in_time": True}
    return row
