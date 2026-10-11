"""M2 knowledge contract: ledger records validate, are shadow-only, append-only, and never overclaim."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import knowledge_contract as kc

rows = kc.read_ledger()
assert rows, "ledger empty"
assert len({r["case_id"] for r in rows}) == len(rows)
for r in rows:
    assert kc.validate(r) == [], (r["case_id"], kc.validate(r))
    assert r["shadow"] is True and r["production_use"] is False
    if r["myalpha_view"]["stance"] != "cannot_judge":
        assert r["supporting"] and r["opposing"] and r["invalidation"] and r["review"]["next_review"]
        assert all(c["result"] in ("compatible", "incompatible", "unverifiable") for c in r["claim_checks"])
# validator catches overclaims and missing parts
bad = dict(rows[0]); bad["unknowns"] = ["verified execution"]
assert any("overclaim" in e for e in kc.validate(bad))
bad2 = dict(rows[0]); bad2.pop("opposing")
assert kc.validate(bad2)
# compatibility checks on canonical data
h = kc.history("VGT")
assert kc.check_price_in_range(h, "2026-08-24", 117.57)["result"] == "compatible"
assert kc.check_price_in_range(h, "2026-08-24", 130.0)["result"] == "incompatible"
assert kc.history("AAPL") is None  # not in the free archive → abstain path
# no consumer of the shadow ledger in production code
for p in ("scripts/server_action_engine.py", "scripts/forward_observation_engine.py", "docs/assets/autonomous-agent.js"):
    assert "shadow_research_cases" not in (ROOT / p).read_text(encoding="utf-8")
print("PASS knowledge contract")
