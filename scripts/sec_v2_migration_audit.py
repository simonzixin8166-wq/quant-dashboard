#!/usr/bin/env python3
"""B4-03 pre-migration attribution audit — read-only (#133, owner instruction 2026-10-15 06:07Z).

Before any consumer moves from the old SEC path to the unified v2 Shadow, every difference must be explained.
No network, nothing in production is written or changed; output is an audit file only.

Three comparisons, one classifier vocabulary (each difference gets exactly one primary cause):
  A. latest   old company_fundamental_memory.json  vs  v2 Shadow latest (same old schema), all metrics
  B. research new sec_fundamentals.json (what daily_research_job reads) vs v2 Shadow, revenue / net income
  C. archive  old research/archive/fundamentals  vs  research/archive/fundamentals_v2 (the rows the outcome memory
              would read after migration), keyed by (metric, unit, start, end)
Causes (explained unless marked):
  agree, v2_more_concepts (v2 keeps every candidate concept; old keeps the first concept only),
  old_non_usd (old kept a non-USD unit; v2 skips it by design), amendment_form (v2 keeps 10-Q/A, 10-K/A),
  ytd_period (non quarter/annual period), restated_value (same period, later filing differs — v2 flags it),
  non_operating_trust (ETF / trust: no operating revenue; new path excludes it by design),
  foreign_ifrs_non_usd (20-F filer reporting in IFRS / non-USD: no us-gaap USD facts on either side),
  not_covered (symbol outside one universe), old_stale_concept (old keeps a discontinued first concept),
  discontinued_concept_both (both sides hold the same long-stale fact: the company stopped tagging that concept),
  cashflow_ytd_lag (10-Q cash-flow lines are YTD; v2 drops YTD periods, so its latest lags to the last discrete
  quarter or is empty — DESIGN DECISION, not a data error), etf_no_companyfacts (ETF / unit trust: companyfacts
  returns HTTP error on BOTH paths),
  v2_selection_ttm (BLOCKER: v2 'latest' picked a trailing-12-month figure printed in a 10-Q over the quarter),
  v2_selection_stale (BLOCKER: v2 'latest' end date is > 400 days older than the company's newest filing),
  unexplained (BLOCKER).
Migration gate: zero BLOCKER differences in A and B, archive differences fully attributed in C, and the comparison
repeated on one full real trading day after the next Daily + QA PASS. Until then: Shadow only.
Output: research/audit/sec_v2_migration_audit.json
"""
from __future__ import annotations
import hashlib, json, sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "docs" / "research" / "company_fundamental_memory.json"
NEW = ROOT / "docs" / "research" / "sec_fundamentals.json"
SHADOW = ROOT / "docs" / "research" / "shadow" / "company_fundamental_memory_v2.json"
OLD_ARCH = ROOT / "research" / "archive" / "fundamentals"
V2_ARCH = ROOT / "research" / "archive" / "fundamentals_v2"
REGISTRY = ROOT / "research" / "audit" / "symbol_registry.json"
OUT = ROOT / "research" / "audit" / "sec_v2_migration_audit.json"
BLOCKERS = {"v2_selection_ttm", "v2_selection_stale", "unexplained"}
CASH_FLOW = {"operating_cash_flow", "capex", "sbc"}
FLOW = {"revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "operating_cash_flow", "capex", "sbc"}
NON_OPERATING_HINT = ("TRUST", "ETF", "FUND", "SPDR", "ISHARES")
STALE_DAYS = 400


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def jsonl(p):
    out = []
    try:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    except Exception:
        pass
    return out


def pkind(start, end):
    if not start:
        return "instant"
    try:
        d = (date.fromisoformat(end) - date.fromisoformat(start)).days
    except Exception:
        return "unknown"
    return "quarter" if 80 <= d <= 100 else ("annual" if 330 <= d <= 380 else "ytd_or_other")


def days_between(a, b):
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except Exception:
        return None


def etf_symbols():
    reg = load(REGISTRY) or {}
    return {k for k, v in (reg.get("symbols") or {}).items() if (v or {}).get("asset_type") == "etf"}


def v2_selection_issue(metric, fact, latest_all):
    """Detect the two known v2 'latest' selection defects on a single selected fact."""
    if not fact:
        return None
    newest = max((str(f.get("filed")) for f in latest_all.values() if f), default=None)
    if newest and days_between(fact.get("end"), newest) is not None and days_between(fact.get("end"), newest) > STALE_DAYS:
        return "v2_selection_stale"
    if metric in FLOW and str(fact.get("form", "")).startswith("10-Q") and pkind(fact.get("start"), fact.get("end")) == "annual" \
            and str(fact.get("fp")) != "FY":
        return "v2_selection_ttm"
    return None


def compare_latest(old_doc, v2_doc):
    os_, vs_ = (old_doc or {}).get("symbols") or {}, (v2_doc or {}).get("symbols") or {}
    rows, tally = [], Counter()
    for s in sorted(set(os_) | set(vs_)):
        o, v = (os_.get(s) or {}).get("latest") or {}, (vs_.get(s) or {}).get("latest") or {}
        for m in sorted(set(o) | set(v)):
            of, vf = o.get(m), v.get(m)
            sel = v2_selection_issue(m, vf, v)
            same = bool(of and vf and (of.get("start"), of.get("end"), of.get("value")) == (vf.get("start"), vf.get("end"), vf.get("value")))
            if s not in os_ or s not in vs_:
                cause = "not_covered"
            elif sel == "v2_selection_stale" and of and v2_selection_issue(m, of, o) == "v2_selection_stale":
                cause = "discontinued_concept_both"
            elif sel:
                cause = sel
            elif of is None or vf is None:
                if of is None:
                    cause = "v2_more_concepts"
                elif of.get("unit") not in ("USD", "USD/shares", "shares"):
                    cause = "old_non_usd"
                elif m in CASH_FLOW and pkind(of.get("start"), of.get("end")) == "ytd_or_other":
                    cause = "cashflow_ytd_lag"
                else:
                    cause = "unexplained"
            elif same:
                cause = "agree"
            elif (of.get("start"), of.get("end")) == (vf.get("start"), vf.get("end")):
                if of.get("value") == vf.get("value"):
                    cause = "agree"
                else:
                    cause = "restated_value" if str(vf.get("filed")) > str(of.get("filed")) else "unexplained"
            elif of.get("unit") not in ("USD", "USD/shares", "shares"):
                cause = "old_non_usd"
            elif pkind(of.get("start"), of.get("end")) == "ytd_or_other":
                cause = "cashflow_ytd_lag" if m in CASH_FLOW and str(vf.get("end")) < str(of.get("end")) else "ytd_period"
            elif str(of.get("end")) < str(vf.get("end")):
                cause = "old_stale_concept" if of.get("concept") != vf.get("concept") else "v2_more_concepts"
            elif str(of.get("end")) > str(vf.get("end")):
                cause = "unexplained"
            else:
                cause = "unexplained"
            tally[cause] += 1
            if cause != "agree":
                pick = lambda f: f and {k: f.get(k) for k in ("concept", "unit", "value", "start", "end", "filed", "form", "fp")}
                rows.append({"symbol": s, "metric": m, "cause": cause, "blocker": cause in BLOCKERS, "old": pick(of), "v2": pick(vf)})
    return {"tally": dict(sorted(tally.items())), "differences": rows}


def compare_research(new_doc, v2_doc, etfs=None):
    etfs = etf_symbols() if etfs is None else etfs
    ns_, vs_ = (new_doc or {}).get("symbols") or {}, (v2_doc or {}).get("symbols") or {}
    rows, tally = [], Counter()
    for s in sorted(set(ns_) | set(vs_)):
        n, vnode = ns_.get(s) or {}, vs_.get(s) or {}
        v = vnode.get("latest") or {}
        entity = str(n.get("entity") or vnode.get("company_name") or "").upper()
        for m, nk in (("revenue", "revenue_q"), ("net_income", "net_income_q")):
            nf, vf = n.get(nk), v.get(m)
            sel = v2_selection_issue(m, vf, v)
            if s not in ns_ or s not in vs_:
                cause = "not_covered"
            elif vnode.get("status") == "error" and not n.get("available"):
                cause = ("etf_no_companyfacts" if s in etfs and "fetch failed" in str(n.get("reason"))
                         else "non_operating_trust" if any(h in entity for h in NON_OPERATING_HINT) else "unexplained")
            elif sel:
                cause = sel
            elif nf is None and vf is None:
                reason = str(n.get("reason") or "")
                cause = ("non_operating_trust" if any(h in entity for h in NON_OPERATING_HINT)
                         else "foreign_ifrs_non_usd" if "IFRS" in reason or "foreign" in reason else "unexplained")
            elif nf is None:
                cause = "non_operating_trust" if (s in etfs or any(h in entity for h in NON_OPERATING_HINT)) else "unexplained"
            elif vf is None:
                cause = "unexplained"
            elif (nf.get("start"), nf.get("end")) == (vf.get("start"), vf.get("end")):
                cause = "agree" if nf.get("val") == vf.get("value") else ("restated_value" if str(vf.get("filed")) >= str(nf.get("filed")) else "unexplained")
            else:
                cause = "unexplained"
            tally[cause] += 1
            if cause != "agree":
                rows.append({"symbol": s, "metric": m, "cause": cause, "blocker": cause in BLOCKERS, "entity": n.get("entity"),
                             "new": nf and {k: nf.get(k) for k in ("concept", "val", "start", "end", "filed", "form", "fp")},
                             "v2": vf and {k: vf.get(k) for k in ("concept", "value", "start", "end", "filed", "form", "fp")},
                             "new_reason": n.get("reason")})
    return {"tally": dict(sorted(tally.items())), "differences": rows}


def compare_archives(old_dir, v2_dir):
    out, tot = {}, Counter()
    for p in sorted(Path(old_dir).glob("*.jsonl")):
        s = p.stem
        old, v2 = jsonl(p), jsonl(Path(v2_dir) / f"{s}.jsonl")
        if not v2:
            out[s] = {"cause": "not_covered", "old_rows": len(old)}
            tot["not_covered_symbols"] += 1
            continue
        vkey = defaultdict(set)
        for r in v2:
            vkey[(r.get("metric"), r.get("unit"), r.get("start"), r.get("end"))].add(r.get("value"))
        okey = {(r.get("metric"), r.get("unit"), r.get("start"), r.get("end")) for r in old}
        c = Counter()
        for r in old:
            k = (r.get("metric"), r.get("unit"), r.get("start"), r.get("end"))
            if r.get("metric") == "shares_outstanding":
                c["old_metric_not_in_v2 (shares_outstanding)"] += 1
            elif r.get("unit") not in ("USD", "USD/shares", "shares"):
                c["old_non_usd"] += 1
            elif k not in vkey:
                c["unexplained_missing_in_v2"] += 1
            elif r.get("value") in vkey[k]:
                c["agree"] += 1
            else:
                c["restated_value"] += 1
        extra = Counter()
        for r in v2:
            k = (r.get("metric"), r.get("unit"), r.get("start"), r.get("end"))
            if k in okey:
                continue
            if "/A" in str(r.get("form")):
                extra["amendment_form"] += 1
            elif r.get("period_kind") == "ytd_or_other":
                extra["ytd_period"] += 1
            else:
                extra["v2_more_concepts_or_periods"] += 1
        out[s] = {"old_rows": len(old), "v2_rows": len(v2), "old_vs_v2": dict(c), "v2_only": dict(extra)}
        for k, n in c.items():
            tot[k] += n
    return {"symbols": out, "totals": dict(tot),
            "unexplained_old_rows_missing_in_v2": tot.get("unexplained_missing_in_v2", 0)}


def v2_self_check(v2_doc):
    """D. Every v2 'latest' fact of every symbol (not only overlaps) checked for the two selection defects."""
    issues = []
    for s, n in sorted(((v2_doc or {}).get("symbols") or {}).items()):
        L = n.get("latest") or {}
        for m, f in sorted(L.items()):
            i = v2_selection_issue(m, f, L)
            if i:
                issues.append({"symbol": s, "metric": m, "issue": i, "end": f.get("end"), "start": f.get("start"),
                               "concept": f.get("concept"), "form": f.get("form"), "fp": f.get("fp")})
    return {"issues": issues, "tally": dict(Counter(x["issue"] for x in issues))}


def proposed_latest(rows, newest_filed=None):
    """E. Candidate rule for the B4-03 fix (simulation only; production code is NOT changed):
    - clean rows only (quarter / annual / instant), as today;
    - among rows with the same newest end, a flow metric from a 10-Q (fp != FY) prefers the discrete quarter over a
      trailing-12-month figure; a 10-K (fp FY) keeps the annual figure;
    - a fact whose end is > STALE_DAYS older than the company's newest filing is returned with stale=True so a
      consumer can show it as stale / unavailable instead of 'latest'."""
    best = {}
    for r in rows:
        if r.get("period_kind") == "ytd_or_other":
            continue
        m = r.get("metric")
        rank = (str(r.get("end")), 0 if (m in FLOW and str(r.get("form", "")).startswith("10-Q") and str(r.get("fp")) != "FY"
                                          and r.get("period_kind") == "annual") else 1, str(r.get("filed")))
        if m not in best or rank > best[m][0]:
            best[m] = (rank, r)
    newest = newest_filed or max((str(r.get("filed")) for r in rows), default=None)
    out = {}
    for m, (_, r) in best.items():
        stale = bool(newest and days_between(r.get("end"), newest) is not None and days_between(r.get("end"), newest) > STALE_DAYS)
        out[m] = {**{k: r.get(k) for k in ("concept", "value", "start", "end", "filed", "form", "fp", "period_kind")}, "stale": stale}
    return out


def simulate_fix(v2_dir=V2_ARCH, symbols=None):
    res, tally = {}, Counter()
    for p in sorted(Path(v2_dir).glob("*.jsonl")):
        if symbols and p.stem not in symbols:
            continue
        L = proposed_latest(jsonl(p))
        ttm = [m for m, f in L.items() if m in FLOW and str(f.get("form", "")).startswith("10-Q") and f.get("period_kind") == "annual" and str(f.get("fp")) != "FY"]
        stale = [m for m, f in L.items() if f["stale"]]
        tally["ttm_selected"] += len(ttm); tally["stale_flagged"] += len(stale)
        res[p.stem] = {"ttm_selected": ttm, "stale_flagged": stale}
    return {"symbols": res, "tally": dict(tally),
            "note": "simulation of the candidate rule on the real v2 archive; no production file changed"}


def build(old_doc, new_doc, v2_doc, old_dir=OLD_ARCH, v2_dir=V2_ARCH, now=None, etfs=None):
    now = now or datetime.now(timezone.utc)
    a, b, c = compare_latest(old_doc, v2_doc), compare_research(new_doc, v2_doc, etfs), compare_archives(old_dir, v2_dir)
    d, e = v2_self_check(v2_doc), simulate_fix(v2_dir)
    blockers = [d for part in (a, b) for d in part["differences"] if d["blocker"]]
    decisions = [d for part in (a, b) for d in part["differences"] if d["cause"] == "cashflow_ytd_lag"]
    gate = {"blocker_differences": len(blockers),
            "blocker_causes": dict(Counter(d["cause"] for d in blockers)),
            "blockers": [{k: d[k] for k in ("symbol", "metric", "cause")} for d in blockers],
            "design_decisions_needed": {"cashflow_ytd_lag": sorted({f"{d['symbol']}.{d['metric']}" for d in decisions}),
                                        "question": "should v2 'latest' keep the newest YTD cash-flow figure (old behaviour) or only discrete quarters?"},
            "archive_unexplained_rows": c["unexplained_old_rows_missing_in_v2"],
            "v2_self_check": d["tally"],
            "candidate_fix_simulation": e["tally"],
            "real_trading_day_comparison": "pending (needs the next real Daily + QA PASS)",
            "migration_allowed": False,
            "why": "Shadow only until blockers = 0, archive differences attributed, and one real trading day repeats the result"}
    body = {"generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "inputs": {k: {"path": str(p.relative_to(ROOT)), "generated_at": (d or {}).get("generated_at")}
                       for k, p, d in (("old", OLD, old_doc), ("new", NEW, new_doc), ("v2_shadow", SHADOW, v2_doc))},
            "A_latest_old_vs_v2": a, "B_research_new_vs_v2": b, "C_archive_old_vs_v2": c,
            "D_v2_selection_self_check": d, "E_candidate_fix_simulation": e, "gate": gate,
            "read_only": True, "production_use": False, "consumers_migrated": False}
    body["content_sha256"] = hashlib.sha256(json.dumps({k: body[k] for k in ("A_latest_old_vs_v2", "B_research_new_vs_v2", "C_archive_old_vs_v2")},
                                                       sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return body


def main():
    rep = build(load(OLD), load(NEW), load(SHADOW))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    g = rep["gate"]
    print(f"::notice title=SEC v2 migration audit::blockers={g['blocker_differences']} {g['blocker_causes']} "
          f"archive_unexplained={g['archive_unexplained_rows']} migration_allowed={g['migration_allowed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
