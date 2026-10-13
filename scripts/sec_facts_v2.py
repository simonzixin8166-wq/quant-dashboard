#!/usr/bin/env python3
"""B4-02 — unified SEC fact fetcher, Shadow dual run (#133 6116685851 / 6117308392). Consumers NOT migrated.

One companyfacts fetch per company for the UNION of both current universes:
  old  docs/research/official_evidence.json symbols with a CIK (company_fundamental_memory)
  new  operating symbols of the canonical price archive (sec_fundamentals; ticker → CIK via company_tickers.json)
Every candidate concept of every metric is kept (no "first concept wins"), USD-denominated units only
(USD, USD/shares for EPS; shares for share counts). Non-USD units (e.g. NBIS RUB) are skipped and counted.
Each fact carries period_kind (instant / quarter / annual / ytd_or_other), filed, accn, form, fy/fp and
quality_flags (ytd_or_other_period, restated_value, filed_before_period_end). Rows are appended once
(append-only, idempotent by content hash) to research/archive/fundamentals_v2/<SYMBOL>.jsonl.

A Shadow file in the OLD company_fundamental_memory schema is written to
docs/research/shadow/company_fundamental_memory_v2.json (latest quarter/annual USD fact per metric), so the
two can be compared side by side (sec_fact_reconcile runs daily). Nothing reads the shadow file yet.
Network failures → per-symbol status error; nothing is fabricated. Public SEC data only; free; no API key.
"""
from __future__ import annotations
import hashlib, json, os, sys, time, urllib.request, zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from company_fundamental_memory import CONCEPTS  # noqa: E402  (old metric map; v2 uses every listed concept)
from sec_fundamentals import NON_OPERATING  # noqa: E402

OFFICIAL = ROOT / "docs" / "research" / "official_evidence.json"
PRICE_ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
ARCH = ROOT / "research" / "archive" / "fundamentals_v2"
SHADOW = ROOT / "docs" / "research" / "shadow" / "company_fundamental_memory_v2.json"
TICKERS = "https://www.sec.gov/files/company_tickers.json"
BASE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
UA = os.getenv("SEC_USER_AGENT", "MyAlphaView/6.9 research-agent myalphaview.com")
EXTRA = {"revenue": ["RevenueFromContractWithCustomerIncludingAssessedTax"],
         "net_income": ["NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLossAttributableToParent"]}
ALLOWED_UNITS = {"USD", "USD/shares", "shares"}
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F", "20-F/A", "40-F/A"}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def period_kind(start, end):
    if not start:
        return "instant"
    d = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return "quarter" if 80 <= d <= 100 else ("annual" if 330 <= d <= 380 else "ytd_or_other")


def fact_id(row):
    raw = "|".join(str(row.get(k) or "") for k in ("symbol", "metric", "concept", "unit", "start", "end", "filed", "accn", "form", "value"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def normalize(symbol, payload):
    """All candidate concepts, USD-type units only. Returns (rows, skipped_non_usd_counts)."""
    usg = ((payload.get("facts") or {}).get("us-gaap") or {})
    rows, skipped = [], {}
    for metric, names in CONCEPTS.items():
        for concept in list(names) + EXTRA.get(metric, []):
            for unit, facts in ((usg.get(concept) or {}).get("units") or {}).items():
                if unit not in ALLOWED_UNITS:
                    skipped[unit] = skipped.get(unit, 0) + len(facts)
                    continue
                for u in facts:
                    if u.get("val") is None or not u.get("end") or not u.get("filed") or str(u.get("form")) not in FORMS:
                        continue
                    pk = period_kind(u.get("start"), u["end"])
                    flags = []
                    if pk == "ytd_or_other":
                        flags.append("ytd_or_other_period")
                    if str(u["filed"]) < str(u["end"]):
                        flags.append("filed_before_period_end")
                    row = {"symbol": symbol, "metric": metric, "concept": concept, "unit": unit, "value": u["val"],
                           "start": u.get("start"), "end": u["end"], "period_kind": pk, "filed": u["filed"],
                           "accn": u.get("accn"), "form": u.get("form"), "fy": u.get("fy"), "fp": u.get("fp"),
                           "frame": u.get("frame"), "source": "SEC EDGAR XBRL companyfacts",
                           "point_in_time_available_at": u["filed"], "quality_flags": flags}
                    row["fact_id"] = fact_id(row)
                    rows.append(row)
    # restatement: same (metric, concept, unit, start, end) reported with different values in different filings
    seen = {}
    for r in sorted(rows, key=lambda r: (str(r["filed"]), str(r.get("accn")))):
        k = (r["metric"], r["concept"], r["unit"], r.get("start"), r["end"])
        if k in seen and seen[k] != r["value"]:
            r["quality_flags"].append("restated_value")
            r["restated_from"] = seen[k]
        seen[k] = r["value"]
    rows.sort(key=lambda r: (str(r["filed"]), r["metric"], r["concept"], str(r["end"])))
    return rows, skipped


def append(symbol, rows):
    ARCH.mkdir(parents=True, exist_ok=True)
    p = ARCH / f"{symbol}.jsonl"
    known = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                known.add(json.loads(line)["fact_id"])
            except Exception:
                pass
    added = 0
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            if r["fact_id"] in known:
                continue
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            known.add(r["fact_id"])
            added += 1
    return added, len(known)


def latest_old_schema(rows):
    """Old company_fundamental_memory 'latest' shape, from clean v2 rows only (quarter/annual or instant)."""
    out = {}
    for r in rows:
        if r["period_kind"] == "ytd_or_other":
            continue
        cur = out.get(r["metric"])
        if cur is None or (str(r["end"]), str(r["filed"])) > (str(cur["end"]), str(cur["filed"])):
            out[r["metric"]] = r
    return {m: {"observation_id": r["fact_id"], "symbol": r["symbol"], "metric": m, "concept": r["concept"], "unit": r["unit"],
                "value": r["value"], "start": r.get("start"), "end": r["end"], "filed": r["filed"], "form": r["form"],
                "accn": r.get("accn"), "fy": r.get("fy"), "fp": r.get("fp"), "frame": r.get("frame"),
                "source": "SEC CompanyFacts (v2 shadow)", "point_in_time_available_at": r["filed"], "period_kind": r["period_kind"]}
            for m, r in out.items()}


def universe(official, ticker_map):
    syms = {}
    for s, node in (official.get("symbols") or {}).items():
        if node.get("cik"):
            syms[s] = {"cik": int(node["cik"]), "universes": ["old_official_evidence"]}
    try:
        with zipfile.ZipFile(PRICE_ARCHIVE) as z:
            arch = sorted(n.split("_")[0].upper() for n in z.namelist() if n.endswith("_us_d.csv"))
    except Exception:
        arch = []
    for s in arch:
        if s in NON_OPERATING:
            continue
        cik = ticker_map.get(s)
        if s in syms:
            syms[s]["universes"].append("new_price_archive")
        elif cik:
            syms[s] = {"cik": int(cik), "universes": ["new_price_archive"]}
    return syms


def run(fetch=get_json, official=None, sleep=0.25):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    official = official if official is not None else (json.loads(OFFICIAL.read_text(encoding="utf-8")) if OFFICIAL.exists() else {})
    try:
        tmap = {v["ticker"].upper(): v["cik_str"] for v in fetch(TICKERS).values()}
        tstatus = "ok"
    except Exception as e:
        tmap, tstatus = {}, f"unavailable ({type(e).__name__})"
    syms = universe(official, tmap)
    out = {"version": "2.0-shadow", "generated_at": now, "source": "SEC CompanyFacts/XBRL (unified v2 fetcher, Shadow)",
           "ticker_map": tstatus, "symbols": {}, "consumers_migrated": False}
    totals = {"symbols": len(syms), "ok": 0, "archive_added": 0, "archive_total": 0, "non_usd_skipped": 0,
              "ytd_or_other_rows": 0, "restated_rows": 0}
    for s, meta in sorted(syms.items()):
        try:
            payload = fetch(BASE.format(cik=meta["cik"]))
            rows, skipped = normalize(s, payload)
            added, total = append(s, rows)
            totals["ok"] += 1; totals["archive_added"] += added; totals["archive_total"] += total
            totals["non_usd_skipped"] += sum(skipped.values())
            totals["ytd_or_other_rows"] += sum(1 for r in rows if "ytd_or_other_period" in r["quality_flags"])
            totals["restated_rows"] += sum(1 for r in rows if "restated_value" in r["quality_flags"])
            out["symbols"][s] = {"status": "ok", "cik": meta["cik"], "universes": meta["universes"],
                                 "company_name": payload.get("entityName"), "latest": latest_old_schema(rows),
                                 "observations_seen": len(rows), "archive_total": total, "archive_added": added,
                                 "non_usd_units_skipped": skipped, "fetched_at": now}
        except Exception as e:
            out["symbols"][s] = {"status": "error", "cik": meta["cik"], "universes": meta["universes"],
                                 "error": type(e).__name__, "latest": {}}
        if sleep:
            time.sleep(sleep)
    out["counts"] = totals
    out["guardrails"] = ["Shadow only: no consumer reads this file until a reviewed migration.",
                         "USD-type units only; non-USD facts are skipped and counted, never converted.",
                         "Append-only: a revised fact is a new row; old rows are never rewritten."]
    SHADOW.parent.mkdir(parents=True, exist_ok=True)
    SHADOW.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    o = run()
    c = o["counts"]
    print(f"::notice title=SEC v2 shadow::symbols {c['ok']}/{c['symbols']} added {c['archive_added']} total {c['archive_total']} "
          f"non_usd_skipped {c['non_usd_skipped']} ytd_rows {c['ytd_or_other_rows']} restated {c['restated_rows']} ticker_map {o['ticker_map']}")
