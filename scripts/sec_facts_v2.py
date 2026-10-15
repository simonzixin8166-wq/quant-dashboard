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


PERIOD_CONTRACT = "period-layers-1"
FLOW_METRICS = {"revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capex", "sbc"}
NON_ADDITIVE = {"eps_diluted"}          # per-share values cannot be differenced or summed
STALE_DAYS = 400


def _d(x):
    return date.fromisoformat(str(x)[:10])


def _days(a, b):
    return (_d(b) - _d(a)).days


def _current(rows):
    """One fact per (concept, unit, start, end): the latest-filed value; earlier different values kept as provenance."""
    by = {}
    for r in sorted(rows, key=lambda r: (str(r["filed"]), str(r.get("accn")))):
        k = (r["concept"], r["unit"], r.get("start"), r["end"])
        prev = by.get(k)
        cur = dict(r)
        if prev is not None and prev["value"] != r["value"]:
            cur["restated_from"] = {"value": prev["value"], "filed": prev["filed"], "fact_id": prev["fact_id"]}
        elif prev is not None and prev.get("restated_from"):
            cur["restated_from"] = prev["restated_from"]
        by[k] = cur
    return list(by.values())


def _pub(r, basis, derived_from=None, value=None, start=None, quality=None):
    out = {"value": r["value"] if value is None else value, "start": r.get("start") if start is None else start, "end": r["end"],
           "filed": r["filed"], "available_at": r["filed"], "accn": r.get("accn"), "form": r.get("form"), "fy": r.get("fy"),
           "fp": r.get("fp"), "concept": r["concept"], "currency": r["unit"], "source": "SEC EDGAR XBRL companyfacts",
           "basis": basis, "quality": sorted(set((quality or []) + (["restated_value"] if r.get("restated_from") else [])))}
    out["fact_ids"] = derived_from or [r["fact_id"]]
    if r.get("restated_from"):
        out["restated_from"] = r["restated_from"]
    return out


def period_layers(rows, metric, newest_filed=None):
    """period-layers-1 (#133 6186122456): YTD, Quarter and TTM kept apart, never mixed.
    - YTD: fiscal-year-to-date as filed (10-Q) or the fiscal year (10-K), on the latest period end of the dominant concept.
    - Quarter: reported discrete quarter; else derived = YTD(n) − YTD(n−1) of the SAME fiscal year (same start), same
      concept and currency, contiguous, 80–100 days, the earlier fact filed no later than the later one; derived_from ids.
    - TTM: fiscal-year figure from a 10-K; else a trailing-12-month figure reported in a 10-Q; else derived =
      prior fiscal year + current YTD − prior-year YTD of the same length (all same concept / currency, filed by then).
    Anything that cannot be built this way is {"status": "unavailable", "why": ...}; nothing is guessed or zero-filled.
    A latest period end older than STALE_DAYS vs the company's newest filing marks every layer stale."""
    cand = [r for r in _current(rows) if r["metric"] == metric and r.get("start")]
    if not cand:
        return None
    latest_by_concept = {}
    for r in cand:
        k = (r["concept"], r["unit"])
        latest_by_concept[k] = max(latest_by_concept.get(k, ""), str(r["end"]))
    concept, unit = max(latest_by_concept, key=lambda k: (latest_by_concept[k], sum(1 for r in cand if (r["concept"], r["unit"]) == k)))
    rs = [r for r in cand if (r["concept"], r["unit"]) == (concept, unit)]
    end = latest_by_concept[(concept, unit)]
    fy_starts = {r["start"] for r in rs if str(r.get("form", "")).startswith(("10-K", "20-F", "40-F")) and r["period_kind"] == "annual"}
    ytd_starts = {r["start"] for r in rs if 100 < _days(r["start"], r["end"]) < 330}
    fiscal_starts = fy_starts | ytd_starts
    at_end = [r for r in rs if r["end"] == end]
    newest = newest_filed or max(str(r["filed"]) for r in rows)
    stale = _days(end, newest) > STALE_DAYS
    q = ["stale"] if stale else []
    una = lambda why: {"status": "unavailable", "why": why}
    fiscal_annual = next((r for r in at_end if r["period_kind"] == "annual" and r["start"] in fiscal_starts), None)
    reported_ttm = next((r for r in at_end if r["period_kind"] == "annual" and r["start"] not in fiscal_starts), None)
    shorter = sorted((r for r in at_end if _days(r["start"], r["end"]) < 330), key=lambda r: r["start"])
    ytd_row = fiscal_annual or (shorter[0] if shorter else None)
    ytd = _pub(ytd_row, "fiscal_year" if fiscal_annual else "reported_ytd", quality=q) if ytd_row else una("no fiscal-year-to-date fact at the latest end")
    rq = next((r for r in at_end if r["period_kind"] == "quarter"), None)
    if rq:
        quarter = _pub(rq, "reported", quality=q)
    elif metric in NON_ADDITIVE:
        quarter = una("per-share metric: a quarter cannot be derived by differencing")
    elif ytd_row:
        prev = [r for r in rs if r["start"] == ytd_row["start"] and str(r["end"]) < end and str(r["filed"]) <= str(ytd_row["filed"])]
        prev = max(prev, key=lambda r: str(r["end"])) if prev else None
        qstart = str(date.fromordinal(_d(prev["end"]).toordinal() + 1)) if prev else None
        if prev and 80 <= _days(qstart, end) <= 100:
            quarter = _pub(ytd_row, "derived_ytd_difference", derived_from=[ytd_row["fact_id"], prev["fact_id"]],
                           value=ytd_row["value"] - prev["value"], start=qstart, quality=q + ["derived"])
        else:
            quarter = una("no earlier YTD of the same fiscal year to difference against (e.g. first filing after IPO)")
    else:
        quarter = una("no discrete quarter or YTD at the latest end")
    if fiscal_annual:
        ttm = _pub(fiscal_annual, "fiscal_year", quality=q)
    elif reported_ttm:
        ttm = _pub(reported_ttm, "reported_ttm", quality=q)
    elif metric in NON_ADDITIVE:
        ttm = una("per-share metric: TTM not derived")
    elif ytd_row:
        s0 = _d(ytd_row["start"])
        fy_prev = [r for r in rs if r["period_kind"] == "annual" and r["start"] in fiscal_starts and abs(_days(r["end"], str(s0)) - 1) <= 3
                   and str(r["filed"]) <= str(ytd_row["filed"])]
        ln = _days(ytd_row["start"], end)
        ytd_prev = [r for r in rs if fy_prev and r["start"] == fy_prev[0]["start"] and abs(_days(r["start"], r["end"]) - ln) <= 7
                    and str(r["filed"]) <= str(ytd_row["filed"])]
        if fy_prev and ytd_prev:
            a, y0 = fy_prev[0], max(ytd_prev, key=lambda r: str(r["filed"]))
            ttm = _pub(ytd_row, "derived_fy_plus_ytd", derived_from=[a["fact_id"], ytd_row["fact_id"], y0["fact_id"]],
                       value=a["value"] + ytd_row["value"] - y0["value"],
                       start=str(date.fromordinal(_d(y0["end"]).toordinal() + 1)), quality=q + ["derived"])
        else:
            ttm = una("prior fiscal year and prior-year YTD of the same length are not both available")
    else:
        ttm = una("no fiscal-year or YTD fact at the latest end")
    return {"contract": PERIOD_CONTRACT, "concept": concept, "currency": unit, "latest_end": end, "stale": stale,
            "ytd": ytd, "quarter": quarter, "ttm": ttm}


def latest_old_schema(rows, layers=None):
    """Old company_fundamental_memory 'latest' shape for the Shadow comparison.
    Flow metrics: on a 10-K period end the fiscal year; on a 10-Q end the discrete QUARTER (reported or derived);
    never a TTM printed in a 10-Q and never a multi-quarter YTD (those live in `periods`). Instants: newest instant. Every value carries period_kind / basis / stale."""
    out = {}
    newest = max((str(r["filed"]) for r in rows), default=None)
    layers = layers if layers is not None else {m: period_layers(rows, m, newest) for m in {r["metric"] for r in rows}}
    for m in sorted({r["metric"] for r in rows}):
        L = layers.get(m)
        if L:
            # a 10-K period end → the fiscal year (as the research path reads it); a 10-Q end → the discrete quarter
            pick = L["ytd"] if L["ytd"].get("basis") == "fiscal_year" else (
                L["quarter"] if L["quarter"].get("value") is not None else None)
            if not pick:
                continue
            kind = "annual" if pick.get("basis") == "fiscal_year" else "quarter"
            out[m] = {"observation_id": pick["fact_ids"][0], "symbol": next(r["symbol"] for r in rows), "metric": m,
                      "concept": pick["concept"], "unit": pick["currency"], "value": pick["value"], "start": pick["start"],
                      "end": pick["end"], "filed": pick["filed"], "form": pick["form"], "accn": pick.get("accn"), "fy": pick.get("fy"),
                      "fp": pick.get("fp"), "frame": None, "source": "SEC CompanyFacts (v2 shadow)", "point_in_time_available_at": pick["filed"],
                      "period_kind": kind, "basis": pick["basis"], "derived_from": pick["fact_ids"] if pick["basis"].startswith("derived") else None,
                      "stale": L["stale"], "quality": pick["quality"]}
            continue
        inst = [r for r in _current(rows) if r["metric"] == m and r["period_kind"] == "instant"]
        if not inst:
            continue
        r = max(inst, key=lambda r: (str(r["end"]), str(r["filed"])))
        stale = bool(newest) and _days(r["end"], newest) > STALE_DAYS
        out[m] = {"observation_id": r["fact_id"], "symbol": r["symbol"], "metric": m, "concept": r["concept"], "unit": r["unit"],
                  "value": r["value"], "start": None, "end": r["end"], "filed": r["filed"], "form": r["form"], "accn": r.get("accn"),
                  "fy": r.get("fy"), "fp": r.get("fp"), "frame": r.get("frame"), "source": "SEC CompanyFacts (v2 shadow)",
                  "point_in_time_available_at": r["filed"], "period_kind": "instant", "basis": "reported", "derived_from": None,
                  "stale": stale, "quality": ["stale"] if stale else []}
    return out


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
    out = {"version": "2.1-shadow", "period_contract": PERIOD_CONTRACT, "generated_at": now, "source": "SEC CompanyFacts/XBRL (unified v2 fetcher, Shadow)",
           "ticker_map": tstatus, "symbols": {}, "consumers_migrated": False}
    totals = {"symbols": len(syms), "ok": 0, "archive_added": 0, "archive_total": 0, "non_usd_skipped": 0,
              "ytd_or_other_rows": 0, "restated_rows": 0}
    for s, meta in sorted(syms.items()):
        try:
            payload = fetch(BASE.format(cik=meta["cik"]))
            rows, skipped = normalize(s, payload)
            newest = max((str(r["filed"]) for r in rows), default=None)
            layers = {m: L for m in sorted(FLOW_METRICS | NON_ADDITIVE) if (L := period_layers(rows, m, newest))}
            added, total = append(s, rows)
            totals["ok"] += 1; totals["archive_added"] += added; totals["archive_total"] += total
            totals["non_usd_skipped"] += sum(skipped.values())
            totals["ytd_or_other_rows"] += sum(1 for r in rows if "ytd_or_other_period" in r["quality_flags"])
            totals["restated_rows"] += sum(1 for r in rows if "restated_value" in r["quality_flags"])
            out["symbols"][s] = {"status": "ok", "cik": meta["cik"], "universes": meta["universes"],
                                 "company_name": payload.get("entityName"), "latest": latest_old_schema(rows, layers),
                                 "periods": layers,
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
