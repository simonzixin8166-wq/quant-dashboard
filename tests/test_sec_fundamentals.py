"""SEC fact quality gate: concept switches, no period mixing, freshness, coverage denominators."""
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sec_fundamentals as sf

def u(start, end, val, filed, form="10-Q", accn="a"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": accn, "fy": 2026, "fp": "Q"}

TODAY = date(2026, 10, 11)
# AVGO-like: revenue current (2026), NetIncomeLoss quarterly only until 2019 → net income must be unavailable, never 2019
avgo = {"entityName": "Broadcom Inc.", "facts": {"us-gaap": {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [u("2025-05-05", "2025-08-03", 16e9, "2025-09-10"), u("2026-05-04", "2026-08-02", 20e9, "2026-09-10")]}},
    "NetIncomeLoss": {"units": {"USD": [u("2019-05-06", "2019-08-04", 1e9, "2019-09-13")]}}}}}
sf.get = lambda url: avgo
r = sf.facts_for("AVGO", 1730168, TODAY)
assert r["available"] and r["revenue_q"]["end"] == "2026-08-02" and abs(r["revenue_yoy"] - 0.25) < 1e-9
assert r["net_income_q"] is None and r["metrics_status"]["net_income"].startswith("unavailable")
# NVDA-like: concept switch — old concept stops in 2022, new concept continues to 2026 → must use 2026
nvda = {"entityName": "NVIDIA", "facts": {"us-gaap": {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [u("2021-02-01", "2022-01-30", 26e9, "2022-03-18", "10-K")]}},
    "Revenues": {"units": {"USD": [u("2025-04-28", "2025-07-27", 46e9, "2025-08-27"), u("2026-04-27", "2026-07-26", 60e9, "2026-08-26")]}},
    "NetIncomeLoss": {"units": {"USD": [u("2026-04-27", "2026-07-26", 30e9, "2026-08-26")]}}}}}
sf.get = lambda url: nvda
r = sf.facts_for("NVDA", 1045810, TODAY)
assert r["revenue_q"]["end"] == "2026-07-26" and r["revenue_concept"] == "Revenues" and r["net_income_q"]["val"] == 30e9
assert r["metrics_status"]["revenue"] == "current"
# GOOG-like: latest period 2025-03-31 → stale, not current evidence
goog = {"entityName": "Alphabet", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [u("2025-01-01", "2025-03-31", 90e9, "2025-04-25")]}}}}}
sf.get = lambda url: goog
r = sf.facts_for("GOOG", 1652044, TODAY)
assert r["available"] is False and r["freshness"]["status"] == "stale" and "stale" in r["reason"]
# IFRS / no us-gaap revenue → unavailable with reason
sf.get = lambda url: {"entityName": "TSMC", "facts": {"ifrs-full": {}}}
r = sf.facts_for("TSM", 1046179, TODAY)
assert r["available"] is False and "no USD revenue facts" in r["reason"]
# annual-only latest period (10-K) is used when it ends after the latest quarter
iren = {"entityName": "IREN", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
    u("2025-01-01", "2025-03-31", 100, "2025-05-10"), u("2024-07-01", "2025-06-30", 500, "2025-08-28", "10-K"), u("2025-07-01", "2026-06-30", 707, "2026-08-27", "10-K")]}},
    "NetIncomeLoss": {"units": {"USD": [u("2025-07-01", "2026-06-30", -702, "2026-08-27", "10-K")]}}}}}
sf.get = lambda url: iren
r = sf.facts_for("IREN", 1878848, TODAY)
assert r["period_type"] == "fiscal_year" and r["net_income_q"]["val"] == -702 and r["available"]
print("PASS sec fundamentals quality gate")
sofi = {"entityName": "SoFi", "facts": {"us-gaap": {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [u("2026-04-01", "2026-06-30", 153e6, "2026-07-30")]}},
    "NetIncomeLoss": {"units": {"USD": [u("2026-04-01", "2026-06-30", 156e6, "2026-07-30")]}}}}}
sf.get = lambda url: sofi
r = sf.facts_for("SOFI", 1818874, TODAY)
assert r["available"] is False and r["metrics_status"]["revenue"].startswith("anomaly_review")
goog2 = {"entityName": "Alphabet", "facts": {"us-gaap": {
    "Revenues": {"units": {"USD": [u("2026-04-01", "2026-06-30", 120e9, "2026-07-23")]}},
    "NetIncomeLoss": {"units": {"USD": [u("2026-04-01", "2026-06-30", 112e9, "2026-07-23")]}}}}}
sf.get = lambda url: goog2
r = sf.facts_for("GOOG", 1652044, TODAY)
assert r["available"] and r["metrics_status"]["net_income"].startswith("anomaly_review")
print("PASS sec sanity")
