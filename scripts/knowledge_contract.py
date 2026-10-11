#!/usr/bin/env python3
"""MyAlpha knowledge contract v1: build, validate and re-check shadow research cases (#133 M2).

  build  <spec.json> : compute market evidence, claim compatibility checks and the rule-based trend view
                       for a case spec, validate it, and append it to the shadow ledger (append-only).
  validate           : validate every ledger record against the contract.
  status             : re-evaluate invalidation conditions on the latest archived closes (no writes).

Market data: data/history/stooq_watchlist.zip (canonical daily OHLC), docs/data.json trend_pulse and
market_indicators, docs/research/auto_thesis_drafts.json (SEC filings). No network, no paid data.
Cases are shadow-only: production_use is always false.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, sys, zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
DATA = ROOT / "docs" / "data.json"
DRAFTS = ROOT / "docs" / "research" / "auto_thesis_drafts.json"
LEDGER = ROOT / "research" / "knowledge" / "shadow_research_cases.jsonl"
VERSION = "knowledge-contract-1"
REQUIRED = ["case_id", "contract_version", "created_at", "analyst", "symbol", "sources", "author_claims", "claim_checks",
            "evidence", "myalpha_view", "supporting", "opposing", "applies_when", "invalidation", "unknowns", "review",
            "shadow", "production_use"]
STANCES = {"bullish", "neutral", "bearish", "cannot_judge"}


def history(symbol):
    name = f"{symbol.lower()}_us_d.csv"
    with zipfile.ZipFile(ARCHIVE) as z:
        if name not in z.namelist():
            return None
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8")))
    return [{"d": r["Date"], "o": float(r["Open"]), "h": float(r["High"]), "l": float(r["Low"]), "c": float(r["Close"])} for r in rows]


def sma(rows, k, n):
    if k + 1 < n:
        return None
    return sum(r["c"] for r in rows[k - n + 1:k + 1]) / n


def at(rows, day):
    for k, r in enumerate(rows):
        if r["d"] == day:
            return k
    return None


# ---- claim compatibility checks (market data can only show compatibility, never prove a trade) ----
def check_price_in_range(rows, day, price):
    k = at(rows, day)
    if k is None:
        return {"result": "unverifiable", "observed": f"no session {day} in archive"}
    r = rows[k]
    ok = r["l"] - 1e-6 <= price <= r["h"] + 1e-6
    return {"result": "compatible" if ok else "incompatible", "observed": f"{day} range {r['l']}–{r['h']}, close {r['c']}"}


def check_close_near(rows, day, price, tol=0.01):
    k = at(rows, day)
    if k is None:
        return {"result": "unverifiable", "observed": f"no session {day} in archive"}
    c = rows[k]["c"]
    return {"result": "compatible" if abs(c / price - 1) <= tol else "incompatible", "observed": f"{day} close {c}"}


def check_close_vs_ma(rows, day, n, side):
    k = at(rows, day)
    m = sma(rows, k, n) if k is not None else None
    if m is None:
        return {"result": "unverifiable", "observed": "insufficient history"}
    c = rows[k]["c"]
    ok = c < m if side == "below" else c > m
    return {"result": "compatible" if ok else "incompatible", "observed": f"{day} close {c} vs MA{n} {m:.2f}"}


def check_ytd_return(rows, day, pct, tol=0.01):
    k = at(rows, day)
    base = [r for r in rows if r["d"] < f"{day[:4]}-01-01"]
    if k is None or not base:
        return {"result": "unverifiable", "observed": "insufficient history"}
    ytd = rows[k]["c"] / base[-1]["c"] - 1
    return {"result": "compatible" if abs(ytd - pct) <= tol else "incompatible",
            "observed": f"{day} close {rows[k]['c']} vs {base[-1]['d']} close {base[-1]['c']}: {ytd:+.2%}"}


def check_no_price(rows, note):
    return {"result": "unverifiable", "observed": note}


CHECKS = {"no_price": check_no_price, "price_in_range": check_price_in_range, "close_near": check_close_near,
          "close_vs_ma": check_close_vs_ma, "ytd_return": check_ytd_return}


# ---- MyAlpha rule-based trend view (computed, not copied from the author) ----
def trend_metrics(symbol, rows):
    k = len(rows) - 1
    tp = (json.loads(DATA.read_text(encoding="utf-8")).get("trend_pulse") or {}).get(symbol) or {}
    m = {"close": rows[k]["c"], "as_of": rows[k]["d"], "ma21": sma(rows, k, 21), "ma50": sma(rows, k, 50), "ma200": sma(rows, k, 200),
         "high_60": max(r["h"] for r in rows[-60:]), "low_60": min(r["l"] for r in rows[-60:]),
         "trend_pulse_state": tp.get("state"), "weekly": tp.get("weekly"), "structure": tp.get("structure"),
         "adx": tp.get("adx"), "rsi": tp.get("rsi"), "trend_pulse_as_of": tp.get("date")}
    for n in (50, 200):
        m[f"dist_ma{n}"] = (m["close"] / m[f"ma{n}"] - 1) if m[f"ma{n}"] else None
    return m


def rule_view(m):
    """Simple, auditable trend stance. Strong-trend gates are deliberately strict; mixed → neutral."""
    above50, above200 = m["close"] > m["ma50"], m["close"] > m["ma200"]
    weekly_up = m.get("weekly") == "多头"
    if above50 and above200 and weekly_up:
        stance = "bullish"
        if (m.get("dist_ma200") or 0) > 0.15 or m.get("trend_pulse_state") == "高位钝化":
            stance = "neutral"  # uptrend but stretched / momentum fading: no new long thesis
    elif not above50 and not above200 and not weekly_up:
        stance = "bearish"
    else:
        stance = "neutral"
    return stance


def market_context():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    vix = (d.get("market_indicators") or {}).get("vix") or {}
    return {"name": "VIX close", "value": vix.get("close"), "source": "docs/data.json market_indicators", "as_of": vix.get("date")}


def filings(symbol):
    try:
        s = json.loads(DRAFTS.read_text(encoding="utf-8"))["symbols"].get(symbol) or {}
    except Exception:
        return None
    off = (s.get("sources") or {}).get("official") or []
    if not off:
        return None
    return {"name": "SEC filings on record", "value": "; ".join(f"{x['form']} {x['date']}" for x in off[:3]),
            "source": "docs/research/auto_thesis_drafts.json (SEC EDGAR)", "as_of": off[0]["date"]}


def build(spec):
    sym = spec["symbol"]
    rows = history(sym)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    case = {"case_id": spec["case_id"], "contract_version": VERSION, "created_at": now, "analyst": spec["analyst"],
            "symbol": sym, "sources": spec["sources"], "author_claims": spec["author_claims"],
            "shadow": True, "production_use": False}
    if rows is None:  # abstain: no canonical free history for this symbol
        case.update({"claim_checks": [{"claim": c["claim"], "check": c["check"], "data_source": "stooq_watchlist.zip",
                                       "data_as_of": None, "observed": "symbol not in free canonical archive", "result": "unverifiable"}
                                      for c in spec.get("checks", [])],
                     "evidence": [], "myalpha_view": {"stance": "cannot_judge", "basis": "rule", "agrees_with_author": "n/a",
                                                      "summary": spec.get("abstain_summary", "No canonical price history: cannot check the claim or form a view.")},
                     "supporting": [], "opposing": [], "applies_when": [], "invalidation": [],
                     "unknowns": spec.get("unknowns", []) + [f"{sym} daily history is not in data/history/stooq_watchlist.zip"],
                     "review": {"next_review": None, "horizon_sessions": None, "status": "abstained",
                                "reopen_when": f"{sym} is added to the canonical free price archive"}})
        return case
    checks = []
    for c in spec.get("checks", []):
        res = CHECKS[c["check"]](rows, **c["args"])
        checks.append({"claim": c["claim"], "check": c["check"], "data_source": "data/history/stooq_watchlist.zip",
                       "data_as_of": rows[-1]["d"], **res})
    m = trend_metrics(sym, rows)
    ev = [{"name": k, "value": (round(v, 4) if isinstance(v, float) else v), "source": "stooq_watchlist.zip" if k not in
           ("trend_pulse_state", "weekly", "structure", "adx", "rsi", "trend_pulse_as_of") else "docs/data.json trend_pulse",
           "as_of": m["trend_pulse_as_of"] if k in ("trend_pulse_state", "weekly", "structure", "adx", "rsi") else m["as_of"]}
          for k, v in m.items() if k not in ("as_of", "trend_pulse_as_of")]
    ev.append(market_context())
    f = filings(sym)
    if f:
        ev.append(f)
    stance = rule_view(m)
    review_on = tc.add_sessions(date.fromisoformat(m["as_of"]), spec.get("horizon_sessions", 20)).isoformat()
    case.update({"claim_checks": checks, "evidence": ev,
                 "myalpha_view": {"stance": stance, "basis": "rule", "agrees_with_author": spec["agrees_with_author"],
                                  "summary": spec["view_summary"].format(**{k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()},
                                                                         dist_ma50_pct=f"{m['dist_ma50']:.1%}", dist_ma200_pct=f"{m['dist_ma200']:.1%}",
                                                                         stance={"bullish": "看多", "neutral": "中性", "bearish": "偏空"}[stance])},
                 "supporting": spec["supporting"], "opposing": spec["opposing"], "applies_when": spec["applies_when"],
                 "invalidation": [{**x, "value": round(m[x["value"]], 2) if isinstance(x.get("value"), str) and x["value"] in m else x.get("value")}
                                  for x in spec["invalidation"]],
                 "unknowns": spec["unknowns"],
                 "review": {"next_review": review_on, "horizon_sessions": spec.get("horizon_sessions", 20), "status": "active",
                            "recheck": "daily invalidation check on archived closes (knowledge_contract.py status)"}})
    return case


def validate(case):
    errs = [f"missing {k}" for k in REQUIRED if k not in case]
    if errs:
        return errs
    if case["shadow"] is not True or case["production_use"] is not False:
        errs.append("cases must be shadow-only")
    v = case["myalpha_view"]
    if v.get("stance") not in STANCES:
        errs.append("bad stance")
    if v.get("stance") != "cannot_judge":
        for k in ("supporting", "opposing", "invalidation"):
            if not case[k]:
                errs.append(f"{k} empty for a non-abstained view")
        if not case["review"].get("next_review"):
            errs.append("no next_review")
        if not case["evidence"]:
            errs.append("no evidence")
    elif not case["unknowns"]:
        errs.append("abstention must list missing evidence")
    for c in case["claim_checks"]:
        if c.get("result") not in ("compatible", "incompatible", "unverifiable"):
            errs.append("bad check result")
    text = json.dumps(case, ensure_ascii=False)
    for banned in ("verified execution", "已核实成交", "confirmed trade"):
        if banned in text:
            errs.append(f"overclaim: {banned}")
    for s in case["sources"]:
        if len(s.get("locator") or "") > 40 or len(s.get("text_sha256") or "") != 64:
            errs.append("source must carry sha256 and ≤40-char locator only")
    return errs


def status(case):
    if case["review"]["status"] == "abstained":
        return "abstained"
    rows = history(case["symbol"])
    last = rows[-1]
    k = len(rows) - 1
    vals = {"close": last["c"], "ma50": sma(rows, k, 50), "ma200": sma(rows, k, 200)}
    for x in case["invalidation"]:
        cur = vals.get(x["metric"])
        ref = vals.get(x.get("ref")) if x.get("ref") else x.get("value")
        if cur is None or ref is None:
            continue
        hit = cur < ref if x["op"] == "<" else cur > ref
        if hit:
            return f"invalidated ({x['metric']} {x['op']} {x.get('ref') or ref} on {last['d']})"
    if case["review"]["next_review"] and last["d"] >= case["review"]["next_review"]:
        return "review_due"
    return "active"


def read_ledger():
    return [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()] if LEDGER.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("spec")
    sub.add_parser("validate"); sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        case = build(json.loads(Path(a.spec).read_text(encoding="utf-8")))
        errs = validate(case)
        if errs:
            print(json.dumps({"case_id": case["case_id"], "errors": errs}, ensure_ascii=False)); return 1
        if any(r["case_id"] == case["case_id"] for r in read_ledger()):
            print(json.dumps({"case_id": case["case_id"], "skipped": "already in ledger (append-only)"})); return 0
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
        print(json.dumps({"case_id": case["case_id"], "stance": case["myalpha_view"]["stance"],
                          "checks": [c["result"] for c in case["claim_checks"]], "review": case["review"]}, ensure_ascii=False))
        return 0
    rows = read_ledger()
    if a.cmd == "validate":
        bad = {r["case_id"]: validate(r) for r in rows if validate(r)}
        print(json.dumps({"cases": len(rows), "invalid": bad}, ensure_ascii=False)); return 1 if bad else 0
    print(json.dumps({r["case_id"]: status(r) for r in rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
