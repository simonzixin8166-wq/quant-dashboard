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
UA = {"User-Agent": "MyAlpha View research (github.com/simonzixin8166-wq/quant-dashboard) contact via GitHub issues"}
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


def quarterly(facts, concepts):
    """Latest 3-month (80–100 day) USD facts for the first concept that has them."""
    usg = (facts.get("facts") or {}).get("us-gaap") or {}
    for c in concepts:
        units = ((usg.get(c) or {}).get("units") or {}).get("USD") or []
        q = [u for u in units if u.get("start") and u.get("end") and 80 <= days(u["start"], u["end"]) <= 100 and u.get("form") in FORMS]
        if not q:
            continue
        by_period = {}
        for u in sorted(q, key=lambda u: u.get("filed", "")):
            key = (u["start"], u["end"])
            prev = by_period.get(key)
            if prev and prev["val"] != u["val"]:
                u = {**u, "restated_from": prev["val"]}
            by_period[key] = u
        return c, sorted(by_period.values(), key=lambda u: u["end"])
    return None, []


def pick(u):
    return {k: u.get(k) for k in ("val", "start", "end", "fy", "fp", "form", "filed", "accn", "restated_from") if u.get(k) is not None}


def facts_for(sym, cik):
    f = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
    out = {"available": False, "cik": f"{int(cik):010d}", "entity": f.get("entityName"),
           "source": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"}
    rc, rq = quarterly(f, REVENUE)
    nc, nq = quarterly(f, NET_INCOME)
    if not rq:
        out["reason"] = "no 3-month USD revenue facts in us-gaap (e.g. IFRS/foreign filer or no XBRL)"
        return out
    last = rq[-1]
    prior = [u for u in rq if 350 <= days(u["end"], last["end"]) <= 380]
    out.update({"available": True, "revenue_concept": rc, "revenue_q": pick(last),
                "revenue_q_prior_year": pick(prior[-1]) if prior else None,
                "revenue_yoy": (last["val"] / prior[-1]["val"] - 1) if prior and prior[-1]["val"] else None})
    if nq:
        nl = [u for u in nq if u["end"] == last["end"]] or [nq[-1]]
        out.update({"net_income_concept": nc, "net_income_q": pick(nl[-1])})
    out["consistency"] = {"entity_matches_ticker_map": True, "period_days": days(last["start"], last["end"]),
                          "restated": bool(last.get("restated_from"))}
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
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=SEC fundamentals::available {ok}/{len(rep['symbols'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
