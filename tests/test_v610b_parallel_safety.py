import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import playbook_config as pc
import range_intelligence as ri
import private_guardrail as pg

# Stabilization contract: production rule registry is frozen in V6.10b.
EXPECTED = {
    "CP-01": "4f24ed13ed3f30ff8e8d1559c0fbfd5bd0a824055afcc99f3f9a04dd6974f64e",
    "CP-02": "5e3ff8164472c67dc93ac31f5791431a0ac755ba7078782f6fdb9475b43d3d32",
    "CP-03": "9f6bf95fb7580a5c056f09c1a13e0c6216677b56f13a7b10c57a9c2821543886",
}
# Recompute expected hashes from the V6.10a baseline source when this test is first
# introduced; subsequent V6.10b changes must not alter them.
actual = {k: pc.rule_hash(k) for k in EXPECTED}
if actual != EXPECTED:
    # Compatibility for repositories whose canonical JSON serialization differs:
    # fail with explicit values so reviewers can verify against the V6.10a PR.
    raise AssertionError(f"V6.10a production rule hashes changed or baseline constants need review: {actual}")

# Range Intelligence must remain a pure research surface.
def row(rsi=55, dd=-0.02, d200=0.10):
    return {"date":"2026-10-02","close":100,"rsi":rsi,"strategy_drawdown":dd,"dist_200ma":d200}

data={"spy_date":"2026-10-02","core":{"QQQM":row(72,-0.01,0.23),"VGT":row(55,-0.02,0.10),"QLD":row(38,-0.08,0.02),"TQQQ":row(30,-0.18,-0.09)},"index":{"QQQ":row(55,-0.02,0.10),"SMH":row(55,-0.02,0.10)}}
payload=ri.build(data=data, playbook={"version":"6.10a.0"}, now=datetime(2026,10,3,12,0,tzinfo=timezone.utc))
assert payload["mode"]=="research_only"
assert payload["production_semantics_frozen"] is True
states={x["symbol"]:x["state"] for x in payload["assets"]}
assert states["QQQM"]=="RANGE_EXTENDED"
assert states["VGT"]=="RANGE_BALANCED"
assert states["QLD"]=="RANGE_PULLBACK"
assert states["TQQQ"]=="RANGE_STRESS"
assert all(x["research_only"] and not x["scoreable"] and not x["ledger_write"] for x in payload["assets"])

# Public tree must pass the fail-closed private material scan.
assert pg.scan()==[], pg.scan()

print("PASS V6.10b parallel safety / Range Intelligence / Private Guardrail")
