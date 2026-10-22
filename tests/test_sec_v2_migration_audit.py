"""B4-03 pre-migration audit: every difference gets one cause; blockers are TTM / stale v2 selection and unexplained;
the candidate selection rule is a simulation only. Fixture data; no network, no production file written."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sec_v2_migration_audit as a  # noqa: E402


def f(v, s, e, filed, form="10-Q", fp="Q2", concept="NetIncomeLoss", unit="USD"):
    return {"value": v, "start": s, "end": e, "filed": filed, "form": form, "fp": fp, "concept": concept, "unit": unit}


old = {"symbols": {
    "AAA": {"latest": {"revenue": f(10, "2026-04-01", "2026-06-30", "2026-07-30", concept="Revenues"),
                       "net_income": f(9, "2026-01-01", "2026-06-30", "2026-07-30"),                       # YTD 6 months
                       "capex": f(5, "2026-01-01", "2026-06-30", "2026-07-30", concept="PaymentsToAcquirePropertyPlantAndEquipment"),
                       "cash": f(7, None, "2023-12-31", "2024-04-01", form="20-F", fp="FY", concept="Cash", unit="RUB"),
                       "gross_profit": f(3, "2018-06-01", "2018-08-31", "2018-09-19", fp="Q1", concept="GrossProfit")}},
    "OLDONLY": {"latest": {"revenue": f(1, "2026-04-01", "2026-06-30", "2026-07-30")}}}}
v2 = {"symbols": {
    "AAA": {"status": "ok", "latest": {
        "revenue": f(10, "2026-04-01", "2026-06-30", "2026-07-30", concept="Revenues"),                      # agree
        "net_income": f(4, "2026-04-01", "2026-06-30", "2026-07-30"),                                        # old YTD → ytd_period
        "capex": f(2, "2026-01-01", "2026-03-31", "2026-04-30", fp="Q1", concept="PaymentsToAcquirePropertyPlantAndEquipment"),  # cash-flow lag
        "cash": f(8, None, "2025-12-31", "2026-04-30", form="20-F", fp="FY", concept="Cash"),               # old non-USD
        "gross_profit": f(3, "2018-06-01", "2018-08-31", "2018-09-19", fp="Q1", concept="GrossProfit"),     # stale in both
        "sbc": f(6, "2025-07-01", "2026-06-30", "2026-07-30", concept="ShareBasedCompensation")}},           # TTM in 10-Q → blocker
    "BBB": {"status": "ok", "latest": {"net_income": f(5, "2025-07-01", "2026-06-30", "2026-07-31")}},      # TTM in 10-Q
    "ETF": {"status": "error", "latest": {}},
    "GLDX": {"status": "ok", "company_name": "SPDR GOLD TRUST", "latest": {"net_income": f(-1, "2026-04-01", "2026-06-30", "2026-08-04", fp="Q3", concept="ProfitLoss")}},
    "FOR": {"status": "ok", "latest": {}}}}
new = {"symbols": {
    "BBB": {"available": True, "revenue_q": None, "net_income_q": {"val": 2, "start": "2026-04-01", "end": "2026-06-30", "filed": "2026-07-31", "form": "10-Q", "fp": "Q2"}},
    "ETF": {"available": False, "reason": "companyfacts fetch failed: HTTPError"},
    "GLDX": {"available": False, "entity": "SPDR GOLD TRUST", "reason": "no USD revenue facts in us-gaap (e.g. IFRS/foreign filer or no XBRL)"},
    "FOR": {"available": False, "entity": "Foreign Co", "reason": "no USD revenue facts in us-gaap (e.g. IFRS/foreign filer or no XBRL)"}}}

A = a.compare_latest(old, v2)
cause = {(d["symbol"], d["metric"]): d["cause"] for d in A["differences"]}
assert A["tally"]["agree"] == 1
assert cause[("AAA", "net_income")] == "ytd_period" and cause[("AAA", "capex")] == "cashflow_ytd_lag"
assert cause[("AAA", "cash")] == "old_non_usd" and cause[("AAA", "gross_profit")] == "discontinued_concept_both"
assert cause[("AAA", "sbc")] == "v2_selection_ttm" and cause[("OLDONLY", "revenue")] == "not_covered"
B = a.compare_research(new, v2, etfs={"ETF"})
bc = {(d["symbol"], d["metric"]): d["cause"] for d in B["differences"]}
assert bc[("BBB", "net_income")] == "v2_selection_ttm" and bc[("ETF", "revenue")] == "etf_no_companyfacts"
assert bc[("GLDX", "net_income")] == "non_operating_trust" and bc[("FOR", "revenue")] == "foreign_ifrs_non_usd"
assert all(d["blocker"] == (d["cause"] in a.BLOCKERS) for d in A["differences"] + B["differences"])
# an ETF fetch failure that is NOT a known ETF stays unexplained (never silently explained)
assert {(d["symbol"], d["metric"]): d["cause"] for d in a.compare_research(new, v2, etfs=set())["differences"]}[("ETF", "revenue")] == "unexplained"
D = a.v2_self_check(v2)
assert D["tally"] == {"v2_selection_stale": 1, "v2_selection_ttm": 2}

# candidate rule (simulation): quarter beats TTM-in-10-Q at the same end; 10-K keeps annual; stale flagged, not hidden
rows = [dict(f(5, "2025-07-01", "2026-06-30", "2026-07-31"), metric="net_income", period_kind="annual"),
        dict(f(2, "2026-04-01", "2026-06-30", "2026-07-31"), metric="net_income", period_kind="quarter"),
        dict(f(9, "2025-01-01", "2025-12-31", "2026-02-01", form="10-K", fp="FY"), metric="revenue", period_kind="annual"),
        dict(f(1, "2016-01-01", "2016-12-31", "2017-02-01", form="10-K", fp="FY", concept="GrossProfit"), metric="gross_profit", period_kind="annual"),
        dict(f(3, "2026-01-01", "2026-06-30", "2026-07-31"), metric="capex", period_kind="ytd_or_other")]
L = a.proposed_latest(rows)
assert L["net_income"]["value"] == 2 and L["net_income"]["period_kind"] == "quarter" and not L["net_income"]["stale"]
assert L["revenue"]["value"] == 9 and L["gross_profit"]["stale"] is True and "capex" not in L
# archive comparison: non-USD, agree, restated, unexplained missing; v2-only rows attributed
with tempfile.TemporaryDirectory() as t:
    o, v = Path(t) / "old", Path(t) / "v2"
    o.mkdir(); v.mkdir()
    orow = lambda m, val, unit="USD", s="2026-04-01", e="2026-06-30": {"metric": m, "unit": unit, "start": s, "end": e, "value": val}
    (o / "AAA.jsonl").write_text("\n".join(json.dumps(r) for r in [orow("revenue", 10), orow("revenue", 7, unit="RUB"),
                                                                     orow("net_income", 4), orow("capex", 1, s="2020-01-01", e="2020-03-31")]))
    (v / "AAA.jsonl").write_text("\n".join(json.dumps(r) for r in [orow("revenue", 10), orow("net_income", 5),
                                                                     {**orow("revenue", 11, s="2026-01-01"), "form": "10-Q/A"},
                                                                     {**orow("sbc", 1, s="2026-01-01"), "period_kind": "ytd_or_other"}]))
    (o / "ZZZ.jsonl").write_text(json.dumps(orow("revenue", 1)))
    C = a.compare_archives(o, v)
    s = C["symbols"]["AAA"]
    assert s["old_vs_v2"] == {"agree": 1, "old_non_usd": 1, "restated_value": 1, "unexplained_missing_in_v2": 1}, s
    assert s["v2_only"] == {"amendment_form": 1, "ytd_period": 1} and C["symbols"]["ZZZ"]["cause"] == "not_covered"
    assert C["unexplained_old_rows_missing_in_v2"] == 1
    rep = a.build(old, new, v2, o, v, etfs={"ETF"})
    g = rep["gate"]
    assert g["migration_allowed"] is False and g["blocker_differences"] == 3 and g["archive_unexplained_rows"] == 1
    assert rep["read_only"] and rep["consumers_migrated"] is False and "AAA.capex" in g["design_decisions_needed"]["cashflow_ytd_lag"]
    assert a.build(old, new, v2, o, v, etfs={"ETF"})["content_sha256"] == rep["content_sha256"]            # deterministic
# period-layers-1 outputs: a stale-labelled fact is explained (not a blocker); an old YTD 'latest' that equals v2's
# separate YTD layer is explained; a basis-tagged quarter is never re-flagged as TTM
v2b = {"symbols": {"AAA": {"status": "ok", "latest": {
    "net_income": {**f(4, "2026-04-01", "2026-06-30", "2026-07-30"), "basis": "reported"},
    "gross_profit": {**f(3, "2018-06-01", "2018-08-31", "2018-09-19", fp="Q1", concept="GrossProfit"), "stale": True}},
    "periods": {"net_income": {"ytd": {"value": 9, "start": "2026-01-01", "end": "2026-06-30"}}}}}}
cb = {(d["symbol"], d["metric"]): d["cause"] for d in a.compare_latest(old, v2b)["differences"]}
assert cb[("AAA", "net_income")] == "ytd_layer_agree" and cb[("AAA", "gross_profit")] == "discontinued_concept_both"
assert a.v2_selection_issue("gross_profit", {"stale": True, "end": "2018-08-31"}, {}) == "stale_flagged"
assert a.v2_selection_issue("net_income", {"basis": "reported", "form": "10-Q", "start": "2025-07-01", "end": "2026-06-30", "fp": "Q2"}, {}) is None
print("PASS sec v2 migration audit")
