#!/usr/bin/env python3
"""Read-only SEC fact reconciliation — step 1 of unifying the SEC source (#133 6116685851 P1-A).

Compares the two existing SEC companyfacts outputs WITHOUT changing either or any consumer:
  old  docs/research/company_fundamental_memory.json  (+ its append-only archive research/archive/fundamentals/)
  new  docs/research/sec_fundamentals.json            (multi-concept merge, USD only, period-consistent, freshness,
                                                        anomaly_review gate; consumed by daily_research_job)
For every symbol and metric (revenue, net income) it classifies the difference and its cause:
  agree             same period and value
  old_non_usd       old value is not in USD (first unit taken, e.g. NBIS in RUB)
  old_ytd_period    old 'latest' is a year-to-date / non-standard period (not ~quarter or ~year)
  old_stale         old period ends earlier (typically the company switched XBRL concept; old keeps the first concept)
  old_misaligned    old net income period differs from old revenue period
  value_conflict    same period, different value (restatement)
  old_newer         old period ends later than new (new would need review)
  only_old/only_new symbol or metric covered by one side only
and whether the append-only archive already holds the canonical (new) fact. No network; nothing is overwritten.
Anomalies are reported as anomaly_review, never declared false data.
Output: research/audit/sec_fact_reconciliation.json (audit, not a public decision input).
"""
from __future__ import annotations
import hashlib, json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "docs" / "research" / "company_fundamental_memory.json"
NEW = ROOT / "docs" / "research" / "sec_fundamentals.json"
ARCH = ROOT / "research" / "archive" / "fundamentals"
OUT = ROOT / "research" / "audit" / "sec_fact_reconciliation.json"
SHADOW = ROOT / "docs" / "research" / "shadow" / "company_fundamental_memory_v2.json"  # B4-02 unified v2 fetcher
FOCUS = ("AVGO", "NVDA", "GOOG", "IREN", "TSM")
METRICS = (("revenue", "revenue", "revenue_q"), ("net_income", "net_income", "net_income_q"))


def load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def days(a, b):
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except Exception:
        return None


def period_kind(start, end):
    d = days(start, end)
    if d is None:
        return "instant_or_unknown"
    return "quarter" if 80 <= d <= 100 else ("year" if 330 <= d <= 380 else "ytd_or_other")


def old_fact(o):
    if not o:
        return None
    return {"value": o.get("value"), "start": o.get("start"), "end": o.get("end"), "filed": o.get("filed"),
            "concept": o.get("concept"), "unit": o.get("unit"), "form": o.get("form"), "accn": o.get("accn"),
            "period_kind": period_kind(o.get("start"), o.get("end"))}


def new_fact(n):
    if not n:
        return None
    return {"value": n.get("val"), "start": n.get("start"), "end": n.get("end"), "filed": n.get("filed"),
            "concept": n.get("concept"), "unit": "USD", "form": n.get("form"), "accn": n.get("accn"),
            "period_kind": period_kind(n.get("start"), n.get("end"))}


def classify(of, nf, old_rev=None):
    if of is None and nf is None:
        return ["neither"]
    if of is None:
        return ["only_new"]
    if nf is None:
        return ["only_old"]
    out = []
    if of.get("unit") != "USD":
        out.append("old_non_usd")
    if of["period_kind"] == "ytd_or_other":
        out.append("old_ytd_period")
    if old_rev and (of.get("start"), of.get("end")) != (old_rev.get("start"), old_rev.get("end")):
        out.append("old_misaligned")
    if (of.get("start"), of.get("end")) == (nf.get("start"), nf.get("end")):
        if of.get("value") != nf.get("value"):
            out.append("value_conflict")
        elif not out:
            out.append("agree")
    elif str(of.get("end")) < str(nf.get("end")):
        out.append("old_stale")
        if of.get("concept") != nf.get("concept"):
            out.append("concept_switch")
    elif str(of.get("end")) > str(nf.get("end")):
        out.append("old_newer")
    return sorted(set(x for x in out if x))


def archive_index():
    idx = {}
    if not ARCH.exists():
        return idx
    for p in ARCH.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            idx.setdefault((r.get("symbol"), r.get("metric")), []).append(r)
    return idx


def archive_has(rows, nf):
    if not nf:
        return None
    return any(r.get("start") == nf["start"] and r.get("end") == nf["end"] and r.get("value") == nf["value"]
               and r.get("unit") == "USD" for r in rows or [])


def archive_latest(rows):
    """What the old algorithm would call 'latest' from the archive alone (newest filed, then newest end)."""
    if not rows:
        return None
    r = max(rows, key=lambda r: (str(r.get("filed")), str(r.get("end"))))
    return old_fact(r)


def build(old, new, idx, now=None):
    now = now or datetime.now(timezone.utc)
    os_ = (old or {}).get("symbols") or {}
    ns_ = (new or {}).get("symbols") or {}
    symbols = sorted(set(os_) | set(ns_))
    rows, tally = {}, {}
    for s in symbols:
        o, n = os_.get(s) or {}, ns_.get(s) or {}
        entry = {"in_old": s in os_, "in_new": s in ns_, "new_available": n.get("available"),
                 "new_metrics_status": n.get("metrics_status"), "metrics": {}}
        old_rev = old_fact((o.get("latest") or {}).get("revenue"))
        for name, okey, nkey in METRICS:
            of = old_fact((o.get("latest") or {}).get(okey)) if s in os_ else None
            nf = new_fact(n.get(nkey)) if s in ns_ else None
            cls = classify(of, nf, old_rev if name == "net_income" else None)
            arch = idx.get((s, okey))
            entry["metrics"][name] = {"old": of, "new": nf, "classes": cls,
                                      "archive_rows": len(arch or []), "archive_has_new_fact": archive_has(arch, nf),
                                      "archive_units": sorted({str(r.get("unit")) for r in arch or []}),
                                      "archive_concepts": sorted({str(r.get("concept")) for r in arch or []})}
            for c in cls:
                tally.setdefault(name, {}).setdefault(c, 0)
                tally[name][c] += 1
        rows[s] = entry
    focus = {}
    for s in FOCUS:
        e = rows.get(s) or {}
        focus[s] = {"in_old_memory": e.get("in_old", False), "in_new_source": e.get("in_new", False),
                    "old_path_view": {m: (e.get("metrics", {}).get(m, {}).get("old") or archive_latest(idx.get((s, m))))
                                      for m in ("revenue", "net_income")},
                    "old_path_basis": "company_fundamental_memory latest" if e.get("in_old") else
                                      ("archive-only (symbol not in current old run)" if idx.get((s, "revenue")) else "not covered by the old module"),
                    "new_view": {m: e.get("metrics", {}).get(m, {}).get("new") for m in ("revenue", "net_income")},
                    "new_metrics_status": e.get("new_metrics_status"),
                    "classes": {m: e.get("metrics", {}).get(m, {}).get("classes") for m in ("revenue", "net_income")}}
    overlap = sorted(s for s in symbols if rows[s]["in_old"] and rows[s]["in_new"])
    body = {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "inputs": {"old": {"path": str(OLD.relative_to(ROOT)), "generated_at": (old or {}).get("generated_at")},
                   "new": {"path": str(NEW.relative_to(ROOT)), "generated_at": (new or {}).get("generated_at")},
                   "archive": str(ARCH.relative_to(ROOT))},
        "coverage": {"old_symbols": sorted(os_), "new_symbols": sorted(ns_), "overlap": overlap,
                     "only_old": sorted(set(os_) - set(ns_)), "only_new": sorted(set(ns_) - set(os_))},
        "overlap_agreement": {m: sum(1 for s in overlap if rows[s]["metrics"][m]["classes"] == ["agree"]) for m, _, _ in METRICS},
        "class_tally": tally,
        "focus_before_after": focus,
        "symbols": rows,
        "read_only": True, "production_use": False,
        "note": "audit only: neither source nor any consumer is changed; anomaly_review values are held for review, not declared false",
    }
    body["content_sha256"] = hashlib.sha256(json.dumps({k: body[k] for k in ("coverage", "class_tally", "symbols")},
                                                       sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return body


def shadow_section(shadow, new):
    """B4-02 dual run: the unified v2 Shadow (old schema) against the current new source, same classifier."""
    if not shadow:
        return {"status": "not_run_yet"}
    b = build(shadow, new, {})
    return {"status": "compared", "shadow_generated_at": shadow.get("generated_at"), "shadow_counts": shadow.get("counts"),
            "coverage": b["coverage"], "overlap_agreement": b["overlap_agreement"], "class_tally": b["class_tally"],
            "disagreements": {s: {m: e["metrics"][m]["classes"] for m in e["metrics"] if e["metrics"][m]["classes"] != ["agree"]}
                              for s, e in b["symbols"].items() if e["in_old"] and e["in_new"]
                              and any(e["metrics"][m]["classes"] != ["agree"] for m in e["metrics"])}}


def main():
    rep = build(load(OLD), load(NEW), archive_index())
    rep["shadow_v2_vs_new"] = shadow_section(load(SHADOW), load(NEW))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = rep["coverage"]
    print(f"::notice title=SEC reconciliation::overlap {len(c['overlap'])} (old {len(c['old_symbols'])}, new {len(c['new_symbols'])}); "
          f"agree revenue {rep['overlap_agreement']['revenue']}/{len(c['overlap'])}, net income {rep['overlap_agreement']['net_income']}/{len(c['overlap'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
