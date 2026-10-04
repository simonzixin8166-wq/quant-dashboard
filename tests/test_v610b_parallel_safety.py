import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import playbook_config as pc
import range_intelligence as ri
import private_guardrail as pg

# Stabilization contract: hashes captured from the V6.10a production baseline.
LEGACY_CP01_HASH = "ad5eab7a409996693a01eea24dfeb9a2f070a27f535092a7cd079acee14972b9"
EXPECTED_UNCHANGED = {
    "CP-02": "f89277cd0b6f80aa2682799ee45d3c02a0cd76633d855cb0621557bc18db8fb5",
    "CP-03": "20aaf8cf9b5c9dfcc137305750b16ccd04a08f873a4a2ddb83d6ef6ffd99220d",
}
assert {k: pc.rule_hash(k) for k in EXPECTED_UNCHANGED} == EXPECTED_UNCHANGED
assert pc.rule_hash("CP-01") != LEGACY_CP01_HASH
assert pc.CORE_TIERS["QQQM"] == {"t1":0.12,"t2":0.18,"t3":0.25}
assert pc.CORE_TIERS["VGT"] == {"t1":0.15,"t2":0.20,"t3":0.30}
assert pc.CORE_TIERS["QLD"] == {"t1":0.25,"t2":0.35,"t3":0.50}
assert pc.TQQQ_RULES["hard_exit"] == {"vix_ma50_gt": 26, "vix_ma200_gt": 24}

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

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.10b Range Intelligence (research-only)" in workflow
assert "python scripts/range_intelligence.py" in workflow
assert "python scripts/private_guardrail.py" in workflow

status_src=(ROOT/"scripts/system_status_center.py").read_text(encoding="utf-8")
assert '"range_intelligence": ROOT/"docs"/"research"/"range_intelligence.json"' in status_src

manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/range_intelligence.json" in manifest

ui=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.10b Range Intelligence · 区间研究" in ui
assert "Research Only · 不写 Forward Ledger" in ui
assert "state.rangeData" in ui

print("PASS V6.10b parallel safety / Range Intelligence / Private Guardrail / production wiring")
