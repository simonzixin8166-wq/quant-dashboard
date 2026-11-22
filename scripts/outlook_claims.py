#!/usr/bin/env python3
"""External outlook claims ledger + watch (Owner 2026-11-22: back end only, no page).

Records institutions' and authors' dated, numeric forecasts (e.g. "Brent ~78 USD end-2027, GS Macro p.2") as
testable claims, and scores each one against the official series once its horizon has passed, so MyAlpha learns
over time which sources forecast well. Also keeps a small watch of the signals those outlooks point to (Brent vs
80 USD, US investment-grade spread, 10-year yield), read from docs/research/macro_context.json (FRED).

  research/outlook/outlook_claims.jsonl       append-only claims (recorded with source, page, recorded_at)
  research/outlook/outlook_claims_status.json  per-claim status (pending / matured with actual and error) + watch
Nothing here is published on the site, feeds a decision, changes a threshold or places an order. Claims are
external views (experimental_unvalidated); a forecast that matures says only how close the source was.
Missing data stays `unavailable`; annual figures without a series are marked `manual_check` at maturity.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "outlook" / "outlook_claims.jsonl"
OUT = ROOT / "research" / "outlook" / "outlook_claims_status.json"
MACRO = ROOT / "docs" / "research" / "macro_context.json"
VERSION = "outlook-claims-0.1"
WATCH = {"brent": ("DCOILBRENTEU", 80.0, "布伦特油价能否回到 80 美元以下"),
         "ig_spread": ("BAMLC0A0CM", None, "美国投资级公司债利差（AI 融资温度计的代理）"),
         "yield_10y": ("DGS10", 5.0, "10 年期美债收益率与 5% 的关系")}
FIELDS = ("claim_id", "source_author", "source_url", "published_at", "institution", "locator", "metric", "series",
          "kind", "value", "low", "high", "horizon", "note_zh")


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def validate(c: dict) -> list[str]:
    errs = [f for f in ("claim_id", "source_url", "institution", "locator", "metric", "kind", "horizon") if not c.get(f)]
    if c.get("kind") == "point" and not isinstance(c.get("value"), (int, float)):
        errs.append("value")
    if c.get("kind") == "range" and not (isinstance(c.get("low"), (int, float)) and isinstance(c.get("high"), (int, float))):
        errs.append("low/high")
    return errs


def _latest_on_or_before(series: dict, horizon: str):
    """The series' latest observation, if it is on or after the horizon (the claim has matured)."""
    lt = (series or {}).get("latest") or {}
    if lt.get("date") and lt["date"] >= horizon and isinstance(lt.get("value"), (int, float)):
        return lt["date"], float(lt["value"])
    return None


def score(claims: list[dict], macro: dict, today: str) -> list[dict]:
    series = (macro or {}).get("series") or {}
    out = []
    for c in claims:
        row = {k: c.get(k) for k in ("claim_id", "institution", "metric", "series", "kind", "value", "low", "high", "horizon")}
        if c["horizon"] > today:
            row["status"] = "pending"
        elif not c.get("series") or c["series"] == "manual":
            row["status"] = "manual_check"
        else:
            got = _latest_on_or_before(series.get(c["series"]), c["horizon"])
            if not got:
                row["status"] = "unavailable"
            else:
                d, v = got
                row.update(status="matured", actual=v, actual_date=d)
                if c["kind"] == "point":
                    row["error"] = round(v - c["value"], 4)
                else:
                    row["inside_range"] = c["low"] <= v <= c["high"]
        out.append(row)
    return out


def watch(macro: dict) -> dict:
    series = (macro or {}).get("series") or {}
    w = {}
    for key, (sid, level, label) in WATCH.items():
        s = series.get(sid) or {}
        lt = s.get("latest") or {}
        if not isinstance(lt.get("value"), (int, float)):
            w[key] = {"series": sid, "label_zh": label, "status": "unavailable"}
            continue
        item = {"series": sid, "label_zh": label, "status": "ok", "date": lt.get("date"), "value": lt["value"],
                "change_20": (s.get("changes") or {}).get("20")}
        if level is not None:
            item["below_level"] = lt["value"] < level
            item["level"] = level
        w[key] = item
    return w


def build(claims: list[dict], macro: dict, now: datetime) -> dict:
    bad = {c.get("claim_id"): validate(c) for c in claims if validate(c)}
    good = [c for c in claims if c.get("claim_id") not in bad]
    rows = score(good, macro, now.date().isoformat())
    by = {}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    return {"version": VERSION, "generated_at": now.isoformat(timespec="seconds"), "macro_as_of": (macro or {}).get("as_of"),
            "claims": len(claims), "invalid": bad, "by_status": by, "rows": rows, "watch": watch(macro),
            "production_use": False, "published": False,
            "policy_zh": "外部机构与作者的预测，只作后台学习与记录；不上网站、不进判断、不改阈值、不下单。"}


def main() -> int:
    claims = read_jsonl(LEDGER)
    ids = [c.get("claim_id") for c in claims]
    if len(ids) != len(set(ids)):
        print("duplicate claim_id in ledger", file=sys.stderr)
        return 1
    macro = json.loads(MACRO.read_text(encoding="utf-8")) if MACRO.exists() else {}
    rep = build(claims, macro, datetime.now(timezone.utc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("claims", "by_status")} | {"watch": {k: v.get("value") for k, v in rep["watch"].items()}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
