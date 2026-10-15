"""period-layers-1 (#133 6186122456): YTD / Quarter / TTM kept apart; derived values only from same-fiscal-year,
same-concept, same-currency, contiguous facts filed no later; otherwise unavailable or stale — never guessed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sec_facts_v2 as v2  # noqa: E402

N = [0]


def r(metric, val, start, end, filed, form="10-Q", fp="Q2", concept="NetCashProvidedByUsedInOperatingActivities", unit="USD", accn=None):
    N[0] += 1
    row = {"symbol": "ACME", "metric": metric, "concept": concept, "unit": unit, "value": val, "start": start, "end": end,
           "period_kind": v2.period_kind(start, end), "filed": filed, "accn": accn or f"a{N[0]}", "form": form, "fy": 2026, "fp": fp,
           "frame": None, "quality_flags": []}
    row["fact_id"] = v2.fact_id(row)
    return row


OCF = "operating_cash_flow"
# --- 10-Q Q2: cash flow reported only YTD (Q1 = 3 months, H1 = 6 months) → quarter derived, YTD kept, TTM derived
fy25 = r(OCF, 100, "2025-01-01", "2025-12-31", "2026-02-01", form="10-K", fp="FY")
h1_25 = r(OCF, 40, "2025-01-01", "2025-06-30", "2025-08-01")
q1 = r(OCF, 30, "2026-01-01", "2026-03-31", "2026-05-01", fp="Q1")
h1 = r(OCF, 70, "2026-01-01", "2026-06-30", "2026-08-01")
L = v2.period_layers([fy25, h1_25, q1, h1], OCF)
assert L["contract"] == "period-layers-1" and L["latest_end"] == "2026-06-30" and not L["stale"]
assert L["ytd"]["basis"] == "reported_ytd" and L["ytd"]["value"] == 70 and L["ytd"]["start"] == "2026-01-01"
q = L["quarter"]
assert q["basis"] == "derived_ytd_difference" and q["value"] == 40 and (q["start"], q["end"]) == ("2026-04-01", "2026-06-30")
assert q["fact_ids"] == [h1["fact_id"], q1["fact_id"]] and "derived" in q["quality"] and q["available_at"] == "2026-08-01"
t = L["ttm"]
assert t["basis"] == "derived_fy_plus_ytd" and t["value"] == 100 + 70 - 40 and (t["start"], t["end"]) == ("2025-07-01", "2026-06-30")
assert t["fact_ids"] == [fy25["fact_id"], h1["fact_id"], h1_25["fact_id"]] and t["currency"] == "USD"
lat = v2.latest_old_schema([fy25, h1_25, q1, h1])[OCF]
assert lat["period_kind"] == "quarter" and lat["value"] == 40 and lat["derived_from"] == [h1["fact_id"], q1["fact_id"]]

# --- AMZN case: a 10-Q also prints a trailing-12-month figure; latest = reported quarter, TTM layer = reported_ttm
NI = "net_income"
amzn = [r(NI, 135, "2025-07-01", "2026-06-30", "2026-07-31", concept="NetIncomeLoss", accn="x"),
        r(NI, 93, "2026-01-01", "2026-06-30", "2026-07-31", concept="NetIncomeLoss", accn="x"),
        r(NI, 63, "2026-04-01", "2026-06-30", "2026-07-31", concept="NetIncomeLoss", accn="x")]
La = v2.period_layers(amzn, NI)
assert La["quarter"]["basis"] == "reported" and La["quarter"]["value"] == 63
assert La["ttm"]["basis"] == "reported_ttm" and La["ttm"]["value"] == 135 and La["ytd"]["value"] == 93
assert v2.latest_old_schema(amzn)[NI]["value"] == 63 and v2.latest_old_schema(amzn)[NI]["period_kind"] == "quarter"

# --- 10-K end: latest = fiscal year (what the research path reads); Q4 derived = FY − 9M YTD
k9 = r(NI, 60, "2025-07-01", "2026-03-31", "2026-04-25", fp="Q3", concept="NetIncomeLoss")
kfy = r(NI, 90, "2025-07-01", "2026-06-30", "2026-07-30", form="10-K", fp="FY", concept="NetIncomeLoss")
Lk = v2.period_layers([k9, kfy], NI)
assert Lk["ytd"]["basis"] == "fiscal_year" and Lk["ttm"]["basis"] == "fiscal_year" and Lk["ttm"]["value"] == 90
assert Lk["quarter"]["value"] == 30 and Lk["quarter"]["start"] == "2026-04-01"
lk = v2.latest_old_schema([k9, kfy])[NI]
assert lk["period_kind"] == "annual" and lk["value"] == 90 and lk["basis"] == "fiscal_year"

# --- missing data: first filing after an IPO (H1 only) → quarter and TTM unavailable with a reason; no flow 'latest'
ipo = [r(OCF, 50, "2026-01-01", "2026-06-30", "2026-08-04"), r(OCF, 20, "2025-01-01", "2025-06-30", "2026-08-04")]
Li = v2.period_layers(ipo, OCF)
assert Li["ytd"]["value"] == 50 and Li["quarter"]["status"] == "unavailable" and Li["ttm"]["status"] == "unavailable"
assert "why" in Li["quarter"] and OCF not in v2.latest_old_schema(ipo)
# --- gap: Q1 YTD then 9M YTD with H1 missing → 183-day difference is not a quarter → unavailable
gap = [r(OCF, 30, "2026-01-01", "2026-03-31", "2026-05-01", fp="Q1"), r(OCF, 90, "2026-01-01", "2026-09-30", "2026-11-01", fp="Q3")]
assert v2.period_layers(gap, OCF)["quarter"]["status"] == "unavailable"
# --- no future file: the earlier YTD filed AFTER the later one is never used
fut = [r(OCF, 30, "2026-01-01", "2026-03-31", "2026-09-01", fp="Q1"), r(OCF, 70, "2026-01-01", "2026-06-30", "2026-08-01")]
assert v2.period_layers(fut, OCF)["quarter"]["status"] == "unavailable"
# --- TTM needs a prior-year YTD of the same length: H1 vs a prior 9M YTD → unavailable
mism = [fy25, r(OCF, 55, "2025-01-01", "2025-09-30", "2025-11-01", fp="Q3"), q1, h1]
assert v2.period_layers(mism, OCF)["ttm"]["status"] == "unavailable"
# --- currency / concept: one chain only (dominant concept with the newest end), never mixed
mixed = [r(OCF, 999, "2026-01-01", "2026-06-30", "2026-08-01", concept="OldConcept"), r(OCF, 30, "2026-01-01", "2026-03-31", "2026-05-01", fp="Q1"),
         r(OCF, 70, "2026-01-01", "2026-06-30", "2026-08-01"), r(OCF, 5, "2026-04-01", "2026-09-30", "2026-11-01", concept="NewConcept", fp="Q3")]
Lm = v2.period_layers(mixed, OCF)
assert Lm["concept"] == "NewConcept" and Lm["quarter"]["status"] == "unavailable"          # 6-month NewConcept row is not a quarter
# --- restatement: a 10-Q/A changes H1; the current value is used, the original kept as provenance
re1 = r(OCF, 70, "2026-01-01", "2026-06-30", "2026-08-01")
re2 = r(OCF, 72, "2026-01-01", "2026-06-30", "2026-09-15", form="10-Q/A")
Lr = v2.period_layers([q1, re1, re2], OCF)
assert Lr["ytd"]["value"] == 72 and Lr["ytd"]["restated_from"]["value"] == 70 and "restated_value" in Lr["ytd"]["quality"]
assert Lr["quarter"]["value"] == 42
# --- stale: a concept the company stopped tagging is labelled stale, never presented as current
st = [r("capex", 9, "2017-01-01", "2017-03-31", "2017-04-28", fp="Q1", concept="PaymentsToAcquirePropertyPlantAndEquipment"),
      r(OCF, 70, "2026-01-01", "2026-06-30", "2026-08-01")]
Ls = v2.period_layers(st, "capex")
assert Ls["stale"] is True and "stale" in Ls["quarter"]["quality"]
assert v2.latest_old_schema(st)["capex"]["stale"] is True
# --- per-share metric: never differenced or summed
eps = [r("eps_diluted", 1.0, "2026-01-01", "2026-06-30", "2026-08-01", concept="EarningsPerShareDiluted", unit="USD/shares"),
       r("eps_diluted", 0.4, "2026-01-01", "2026-03-31", "2026-05-01", fp="Q1", concept="EarningsPerShareDiluted", unit="USD/shares")]
Le = v2.period_layers(eps, "eps_diluted")
assert Le["quarter"]["status"] == "unavailable" and Le["ttm"]["status"] == "unavailable"
# --- input rows are never modified (append-only facts stay as filed)
before = [dict(x) for x in [fy25, h1_25, q1, h1]]
v2.period_layers([fy25, h1_25, q1, h1], OCF)
assert before == [fy25, h1_25, q1, h1]
print("PASS sec v2 period layers")
