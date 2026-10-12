"""#133 6116685851 P1-A step 1: read-only reconciliation of the two SEC outputs classifies every known failure mode."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sec_fact_reconcile as r  # noqa: E402

def o(v, s, e, c="RevenueFromContractWithCustomerExcludingAssessedTax", u="USD"):
    return {"value": v, "start": s, "end": e, "filed": "2026-08-01", "concept": c, "unit": u, "form": "10-Q"}
def n(v, s, e, c="RevenueFromContractWithCustomerExcludingAssessedTax"):
    return {"val": v, "start": s, "end": e, "filed": "2026-08-01", "concept": c, "form": "10-Q"}

Q = ("2026-04-01", "2026-06-30")
old = {"generated_at": "t", "symbols": {
    "AGR": {"latest": {"revenue": o(10, *Q), "net_income": o(2, *Q, "NetIncomeLoss")}},
    "YTD": {"latest": {"revenue": o(20, "2026-01-01", "2026-06-30"), "net_income": o(4, "2026-01-01", "2026-06-30", "NetIncomeLoss")}},
    "STL": {"latest": {"revenue": o(9, "2025-01-01", "2025-03-31"), "net_income": o(3, "2026-01-01", "2026-06-30", "NetIncomeLoss")}},
    "RUB": {"latest": {"revenue": o(800, "2023-01-01", "2023-12-31", "Revenues", "RUB"), "net_income": o(19, "2023-01-01", "2023-12-31", "NetIncomeLoss", "RUB")}},
    "RST": {"latest": {"revenue": o(11, *Q), "net_income": o(2, *Q, "NetIncomeLoss")}},
    "OLDONLY": {"latest": {"revenue": o(1, *Q)}}}}
new = {"generated_at": "t", "symbols": {
    "AGR": {"available": True, "revenue_q": n(10, *Q), "net_income_q": n(2, *Q, "NetIncomeLoss")},
    "YTD": {"available": True, "revenue_q": n(12, *Q), "net_income_q": n(2, *Q, "NetIncomeLoss")},
    "STL": {"available": True, "revenue_q": n(12, *Q, "Revenues"), "net_income_q": n(11, *Q, "NetIncomeLoss"),
            "metrics_status": {"net_income": "anomaly_review (|net income| > 80% of revenue)"}},
    "RUB": {"available": True, "revenue_q": n(5, "2025-01-01", "2025-12-31", "Revenues"), "net_income_q": n(1, "2025-01-01", "2025-12-31", "NetIncomeLoss")},
    "RST": {"available": True, "revenue_q": n(12, *Q), "net_income_q": n(2, *Q, "NetIncomeLoss")},
    "NVDA": {"available": True, "revenue_q": n(96, *Q, "Revenues")},
    "TSM": {"available": False, "metrics_status": {"revenue": "unavailable"}}}}
idx = {("AGR", "revenue"): [{"start": Q[0], "end": Q[1], "value": 10, "unit": "USD", "concept": "x", "filed": "f"}],
       ("RUB", "revenue"): [{"start": "2023-01-01", "end": "2023-12-31", "value": 800, "unit": "RUB", "concept": "Revenues", "filed": "f"}]}
d = r.build(old, new, idx)
c = lambda s, m: d["symbols"][s]["metrics"][m]["classes"]
assert c("AGR", "revenue") == ["agree"] and c("AGR", "net_income") == ["agree"]
assert c("YTD", "revenue") == ["old_ytd_period"]
assert set(c("STL", "revenue")) == {"old_stale", "concept_switch"}
assert set(c("STL", "net_income")) == {"old_misaligned", "old_ytd_period"}
assert "old_non_usd" in c("RUB", "revenue") and "old_stale" in c("RUB", "revenue")
assert c("RST", "revenue") == ["value_conflict"]
assert c("OLDONLY", "revenue") == ["only_old"] and c("NVDA", "revenue") == ["only_new"]
assert d["symbols"]["AGR"]["metrics"]["revenue"]["archive_has_new_fact"] is True
assert d["symbols"]["RUB"]["metrics"]["revenue"]["archive_has_new_fact"] is False and d["symbols"]["RUB"]["metrics"]["revenue"]["archive_units"] == ["RUB"]
assert d["overlap_agreement"] == {"revenue": 1, "net_income": 2}  # RST: revenue restated, net income agrees
assert d["coverage"]["only_new"] == ["NVDA", "TSM"] and d["coverage"]["only_old"] == ["OLDONLY"]
# anomalies stay anomaly_review (reported, never relabelled as false)
assert "anomaly_review" in d["symbols"]["STL"]["new_metrics_status"]["net_income"]
f = d["focus_before_after"]
assert f["NVDA"]["old_path_basis"] == "not covered by the old module" and f["TSM"]["new_view"]["revenue"] is None
assert d["read_only"] is True and d["production_use"] is False and len(d["content_sha256"]) == 64
print("test_sec_fact_reconcile OK")
