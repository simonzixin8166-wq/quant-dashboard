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
# #133 6137639898: pre-registered Shadow theses from live sources stay inert and never call an author claim verified
for p in sorted((ROOT / "research" / "shadow_theses").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "not_active" in d["status"] and d["production_use"] is False, p.name
    assert d["production_effect"] == "none" and d["promotion_effect"] == "none" and d["automatic_orders"] is False, p.name
    assert d["source"]["url"] and d["source"]["captured_at"] and d["source"]["excerpt_chars_persisted"] <= 360, p.name
    for c in d["author_claims_unverified"]:
        assert not str(c.get("verification", "")).startswith("verified"), (p.name, c)
    t = d["preregistered_test"]
    assert t["locked_at"] and t["window"]["first_session"] and t["settlement"]["rule"] and t["outcomes"]["falsified"], p.name
print("PASS research proposals inert")
