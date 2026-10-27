#!/usr/bin/env python3
"""SEC XBRL fundamentals for MyAlpha automatic research (#133 6109444028 P0-B). Free, official, no API key.

For each operating company in the canonical price universe:
  ticker → CIK (sec.gov/files/company_tickers.json), companyfacts (data.sec.gov/api/xbrl/companyfacts),
  latest 3-month revenue and net income with period start/end, fiscal year/period, form, filed date and
  accession number; same quarter one year earlier → YoY growth. If several filings report the same
  period with different values (restatement), the latest filed value is used and the restatement noted.
Anything missing is recorded as unavailable with the reason — a filing list is never treated as facts.
Output: docs/research/sec_fundamentals.json (public SEC data only).
"""
from __future__ import annotations
import json, sys, time, urllib.request, zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
OUT = ROOT / "docs" / "research" / "sec_fundamentals.json"
import os
try:  # SEC fair-access identity (secret, never persisted)
    from sec_identity import user_agent as sec_user_agent
except ModuleNotFoundError:  # loaded by file path (tests) without scripts/ on sys.path
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from sec_identity import user_agent as sec_user_agent
UA = {"User-Agent": sec_user_agent(), "Accept": "application/json"}  # same identity as company_fundamental_memory
NON_OPERATING = {"QQQ", "QQQM", "QLD", "TQQQ", "VGT", "VOO", "SMH", "SPY", "VIX", "DRAM"}
REVENUE = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax")
NET_INCOME = ("NetIncomeLoss", "ProfitLoss")
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F", "6-K"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode())


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


FRESH_DAYS = {"quarter": 150, "fiscal_year": 460}  # period end must be this recent to count as *current* evidence
NET_INCOME_ALL = NET_INCOME + ("NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLossAttributableToParent")


def series(facts, concepts, lo, hi):
    """Merge USD duration facts across ALL candidate concepts (companies switch concepts over time).
    One value per (start, end): the latest filed wins; a differing earlier value is kept as restated_from."""
    usg = (facts.get("facts") or {}).get("us-gaap") or {}
    rows = []
    for c in concepts:
        for u in ((usg.get(c) or {}).get("units") or {}).get("USD") or []:
            if u.get("start") and u.get("end") and lo <= days(u["start"], u["end"]) <= hi and u.get("form") in FORMS \
                    and str(u.get("filed", "")) >= str(u["end"]):
                rows.append({**u, "concept": c})
    by_period = {}
    for u in sorted(rows, key=lambda u: (u.get("filed", ""), concepts.index(u["concept"]) * -1)):
        key = (u["start"], u["end"])
        prev = by_period.get(key)
        if prev and prev["val"] != u["val"] and prev["concept"] == u["concept"]:
            u = {**u, "restated_from": prev["val"]}
        by_period[key] = u
    return sorted(by_period.values(), key=lambda u: (u["end"], u.get("filed", "")))


def quarterly(facts, concepts, lo=80, hi=100):  # kept for compatibility (first concept wins)
    rows = series(facts, concepts, lo, hi)
    return (rows[-1]["concept"], rows) if rows else (None, [])


def pick(u):
    return {k: u.get(k) for k in ("val", "start", "end", "fy", "fp", "form", "filed", "accn", "concept", "restated_from") if u.get(k) is not None}


def freshness(period_type, end, today):
    age = (today - date.fromisoformat(end)).days
    return {"period_end_age_days": age, "max_days": FRESH_DAYS[period_type],
            "status": "current" if age <= FRESH_DAYS[period_type] else "stale"}


def facts_for(sym, cik, today=None):
    today = today or datetime.now(timezone.utc).date()
    f = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
    out = {"available": False, "cik": f"{int(cik):010d}", "entity": f.get("entityName"),
           "source": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"}
    rq, aq = series(f, REVENUE, 80, 100), series(f, REVENUE, 330, 380)
    if not rq and not aq:
        out["reason"] = "no USD revenue facts in us-gaap (e.g. IFRS/foreign filer or no XBRL)"
        out["metrics_status"] = {"revenue": "unavailable", "net_income": "unavailable"}
        return out
    # latest period by END date; annual only when it ends later than the latest quarter (e.g. Q4 inside a 10-K)
    period, rows, nlo, nhi = "quarter", rq, 80, 100
    if aq and (not rq or aq[-1]["end"] > rq[-1]["end"]):
        period, rows, nlo, nhi = "fiscal_year", aq, 330, 380
    last = rows[-1]
    fr = freshness(period, last["end"], today)
    prior = [u for u in rows if 350 <= days(u["end"], last["end"]) <= 380]
    ni = [u for u in series(f, NET_INCOME_ALL, nlo, nhi) if u["start"] == last["start"] and u["end"] == last["end"]]
    out.update({"period_type": period, "revenue_concept": last["concept"], "revenue_q": pick(last),
                "revenue_q_prior_year": pick(prior[-1]) if prior else None,
                "revenue_yoy": (last["val"] / prior[-1]["val"] - 1) if prior and prior[-1]["val"] else None,
                "net_income_q": pick(ni[-1]) if ni else None,
                "net_income_concept": ni[-1]["concept"] if ni else None,
                "freshness": fr,
                "metrics_status": {"revenue": fr["status"],
                                   "revenue_yoy": fr["status"] if prior else "unavailable (no comparable prior-year period)",
                                   "net_income": fr["status"] if ni else "unavailable (no net income for the same period)"},
                "consistency": {"period_days": days(last["start"], last["end"]), "net_income_same_period": bool(ni),
                                "prior_year_same_length": bool(prior), "restated": bool(last.get("restated_from")),
                                "filed_after_period_end": str(last.get("filed")) >= last["end"]}})
    # internal consistency: |net income| above 80% of revenue is implausible for most operating companies →
    # either a partial revenue concept (e.g. fintech/bank 'revenue from contracts' excludes interest income) or a
    # one-off item; such metrics are held for review instead of being used as evidence
    if ni and last["val"]:
        ratio = ni[-1]["val"] / last["val"]
        out["consistency"]["net_income_to_revenue"] = round(ratio, 3)
        if abs(ratio) > 0.8:
            out["metrics_status"]["net_income"] = "anomaly_review (|net income| > 80% of revenue)"
        if ratio > 1.0:
            out["metrics_status"]["revenue"] = "anomaly_review (revenue concept may be partial: net income exceeds it)"
            out["metrics_status"]["revenue_yoy"] = out["metrics_status"]["revenue"]
    out["available"] = fr["status"] == "current" and out["metrics_status"]["revenue"] == "current"
    if not out["available"]:
        out["reason"] = (f"latest revenue period ends {last['end']} ({fr['period_end_age_days']} days ago > {fr['max_days']}): stale, not current evidence"
                         if fr["status"] != "current" else out["metrics_status"]["revenue"])
    return out


def universe():
    with zipfile.ZipFile(ARCHIVE) as z:
        syms = sorted(n.split("_")[0].upper() for n in z.namelist() if n.endswith("_us_d.csv"))
    return [s for s in syms if s not in NON_OPERATING]


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rep = {"generated_at": now, "source": "SEC EDGAR XBRL companyfacts (official, free)", "symbols": {},
           "non_operating_skipped": sorted(NON_OPERATING)}
    try:
        tick = {v["ticker"].upper(): v["cik_str"] for v in get("https://www.sec.gov/files/company_tickers.json").values()}
    except Exception as e:
        rep["error"] = f"ticker map unavailable: {type(e).__name__}"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"::warning title=SEC fundamentals::ticker map unavailable ({type(e).__name__})")
        return 0
    for s in universe():
        cik = tick.get(s)
        if not cik:
            rep["symbols"][s] = {"available": False, "reason": "ticker not in SEC company_tickers map"}
            continue
        try:
            rep["symbols"][s] = facts_for(s, cik)
        except Exception as e:
            rep["symbols"][s] = {"available": False, "reason": f"companyfacts fetch failed: {type(e).__name__}"}
        time.sleep(0.25)  # well under SEC's 10 requests/second
    ok = sum(1 for v in rep["symbols"].values() if v.get("available"))
    anyh = sum(1 for v in rep["symbols"].values() if v.get("revenue_q"))
    rep["coverage"] = {"operating_symbols": len(rep["symbols"]), "any_historical_revenue": anyh,
                       "current_and_period_consistent_revenue": ok,
                       "net_income_same_period_current": sum(1 for v in rep["symbols"].values()
                                                             if v.get("available") and v.get("net_income_q"))}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=SEC fundamentals::current+consistent {ok}/{len(rep['symbols'])}; any history {anyh}; "
          f"net income same period {rep['coverage']['net_income_same_period_current']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
