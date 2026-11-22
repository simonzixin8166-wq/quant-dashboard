"""Outlook claims ledger (Owner 2026-11-22, back end only): claims validate, stay pending until their horizon,
mature against the FRED series (point -> error, range -> inside), annual figures without a series need a manual
check, the watch reads Brent / IG spread / 10y, and nothing is published or used in decisions."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import outlook_claims as oc  # noqa: E402

claims = [
    {"claim_id": "a", "source_url": "u", "institution": "GS", "locator": "p.2", "metric": "Brent", "series": "DCOILBRENTEU",
     "kind": "point", "value": 78, "horizon": "2027-12-31"},
    {"claim_id": "b", "source_url": "u", "institution": "PGIM", "locator": "p.3", "metric": "Brent", "series": "DCOILBRENTEU",
     "kind": "range", "low": 90, "high": 120, "horizon": "2027-12-31"},
    {"claim_id": "c", "source_url": "u", "institution": "GS", "locator": "p.6", "metric": "US GDP", "series": "manual",
     "kind": "point", "value": 2.4, "horizon": "2028-03-31"},
    {"claim_id": "d", "source_url": "u", "institution": "X", "locator": "", "metric": "m", "series": "DGS10", "kind": "point",
     "horizon": "2027-01-01"},                                                     # invalid: no locator, no value
]
macro = {"as_of": "2027-12-31", "series": {
    "DCOILBRENTEU": {"latest": {"date": "2027-12-31", "value": 82.5}, "changes": {"20": -3.1}},
    "DGS10": {"latest": {"date": "2027-12-31", "value": 4.7}, "changes": {"20": -0.1}}}}

# before the horizon: pending
rep = oc.build(claims, macro, datetime(2026, 11, 22, tzinfo=timezone.utc))
assert rep["invalid"] == {"d": ["locator", "value"]} and rep["by_status"] == {"pending": 3}
# after the horizon: matured / manual check
rep = oc.build(claims, macro, datetime(2028, 4, 1, tzinfo=timezone.utc))
r = {x["claim_id"]: x for x in rep["rows"]}
assert r["a"]["status"] == "matured" and r["a"]["error"] == 4.5 and r["a"]["actual"] == 82.5
assert r["b"]["status"] == "matured" and r["b"]["inside_range"] is False
assert r["c"]["status"] == "manual_check"
# a series whose latest observation is still before the horizon is not matured
early = {"series": {"DCOILBRENTEU": {"latest": {"date": "2027-12-30", "value": 70}}}}
assert oc.score(claims[:1], early, "2028-01-02")[0]["status"] == "unavailable"
# watch
w = rep["watch"]
assert w["brent"]["below_level"] is False and w["brent"]["level"] == 80.0 and w["ig_spread"]["status"] == "unavailable"
assert w["yield_10y"]["below_level"] is True
assert rep["production_use"] is False and rep["published"] is False

# the committed ledger: valid, unique ids, every claim cites a locator and a source url
led = oc.read_jsonl(oc.LEDGER)
assert led and len({c["claim_id"] for c in led}) == len(led) and all(not oc.validate(c) for c in led)
assert not str(oc.OUT).startswith(str(ROOT / "docs"))                             # not published on the site
fred = (ROOT / "scripts" / "update_fred_macro.py").read_text(encoding="utf-8")
assert all(s in fred for s in ("DCOILBRENTEU", "BAMLC0A0CM", "DFEDTARU"))
print("PASS outlook claims: validate, pending -> matured/manual, watch, back end only")
