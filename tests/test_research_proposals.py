"""Research proposals stay inert: no production/promotion effect, backfill never forward."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in sorted((ROOT / "research" / "proposals").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "not_active" in d.get("status", ""), p.name
    assert d.get("production_effect") in ("none", None) or "no" in str(d.get("production_effect")).lower(), p.name
    if "source" in d:
        ing = d["source"].get("ingest") or {}
        assert ing.get("forward_evidence_eligible") is False and ing.get("intake_class") == "historical_backfill", p.name
        assert d.get("automatic_orders") is False and d.get("promotion_effect") == "none", p.name
        claims = json.dumps(d["method_elements"].get("author_claims_unverified"), ensure_ascii=False)
        assert "NOT verified" in claims
print("PASS research proposals inert")
