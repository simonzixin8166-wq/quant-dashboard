"""B4-02: unified SEC v2 Shadow — union universe, all concepts, USD only, period_kind/flags, append-only, idempotent."""
import json, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sec_facts_v2 as v2  # noqa: E402
import sec_fact_reconcile as rec  # noqa: E402

def f(val, start, end, filed, form="10-Q", accn="a1"):
    return {"val": val, "start": start, "end": end, "filed": filed, "form": form, "accn": accn, "fy": 2026, "fp": "Q2"}
payload = {"entityName": "Acme", "facts": {"us-gaap": {
    "Revenues": {"units": {"USD": [f(10, "2025-04-01", "2025-06-30", "2025-08-01"), f(30, "2025-01-01", "2025-09-30", "2025-11-01")]}},
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [f(12, "2026-04-01", "2026-06-30", "2026-08-01"),
                                                                              f(13, "2026-04-01", "2026-06-30", "2026-09-01", "10-Q/A", "a2")]}},
    "NetIncomeLoss": {"units": {"RUB": [f(99, "2026-04-01", "2026-06-30", "2026-08-01")], "USD": [f(2, "2026-04-01", "2026-06-30", "2026-08-01")]}},
    "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [{"val": 5, "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q", "accn": "a1"}]}}}}}
rows, skipped = v2.normalize("ACME", payload)
assert skipped == {"RUB": 1}
assert {r["concept"] for r in rows if r["metric"] == "revenue"} == {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"}  # all concepts
kinds = {(r["concept"], r["end"], r["value"]): (r["period_kind"], r["quality_flags"]) for r in rows}
assert kinds[("Revenues", "2025-09-30", 30)][0] == "ytd_or_other" and "ytd_or_other_period" in kinds[("Revenues", "2025-09-30", 30)][1]
assert "restated_value" in kinds[("RevenueFromContractWithCustomerExcludingAssessedTax", "2026-06-30", 13)][1]
assert kinds[("CashAndCashEquivalentsAtCarryingValue", "2026-06-30", 5)][0] == "instant"
latest = v2.latest_old_schema(rows)
assert latest["revenue"]["value"] == 13 and latest["revenue"]["unit"] == "USD" and latest["net_income"]["unit"] == "USD"

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    v2.ARCH, v2.SHADOW, v2.PRICE_ARCHIVE = t / "v2", t / "shadow.json", t / "px.zip"
    with zipfile.ZipFile(v2.PRICE_ARCHIVE, "w") as z:
        z.writestr("acme_us_d.csv", "Date\n"); z.writestr("newco_us_d.csv", "Date\n"); z.writestr("qqq_us_d.csv", "Date\n")
    official = {"symbols": {"ACME": {"cik": 1}, "OLDCO": {"cik": 2}}}
    def fetch(url):
        if url == v2.TICKERS:
            return {"0": {"ticker": "NEWCO", "cik_str": 3}, "1": {"ticker": "ACME", "cik_str": 1}}
        if url.endswith("CIK0000000002.json"):
            raise OSError("down")
        return payload
    out = v2.run(fetch=fetch, official=official, sleep=0)
    assert set(out["symbols"]) == {"ACME", "OLDCO", "NEWCO"}                       # union; ETF (QQQ) skipped
    assert out["symbols"]["ACME"]["universes"] == ["old_official_evidence", "new_price_archive"]
    assert out["symbols"]["OLDCO"]["status"] == "error" and out["consumers_migrated"] is False
    n1 = sum(1 for _ in (t / "v2" / "ACME.jsonl").open())
    out2 = v2.run(fetch=fetch, official=official, sleep=0)                          # idempotent append-only
    assert sum(1 for _ in (t / "v2" / "ACME.jsonl").open()) == n1 and out2["counts"]["archive_added"] == 0
    shadow = json.loads(v2.SHADOW.read_text())
    sec = rec.shadow_section(shadow, {"symbols": {"ACME": {"available": True, "revenue_q": {"val": 13, "start": "2026-04-01", "end": "2026-06-30",
                                                                                         "filed": "2026-09-01", "concept": "RevenueFromContractWithCustomerExcludingAssessedTax", "form": "10-Q/A"}}}})
    assert sec["status"] == "compared" and sec["overlap_agreement"]["revenue"] == 1
    assert rec.shadow_section(None, {})["status"] == "not_run_yet"
print("test_sec_facts_v2 OK")
