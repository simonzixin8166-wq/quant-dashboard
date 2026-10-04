import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

from v615_step0_audit import audit

source=json.loads((ROOT/"docs"/"data"/"source_intelligence.json").read_text(encoding="utf-8"))
a=audit(source)
b=audit(source)

# Ignore generated time when checking repeatability.
a.pop("generated_at",None)
b.pop("generated_at",None)
assert a==b

assert a["read_only"] is True
assert a["truncation"]["source_intelligence_records_limit"]==800
assert a["truncation"]["source_reading_records_limit"]==800
assert a["truncation"]["operation_cases_limit"]==120
assert a["truncation"]["normalized_total_records"]>=a["truncation"]["source_intelligence_records_exposed"]
assert "runtime content-hash assertion" in a["operation_consistency"]["finding"]

print("PASS V6.15 Step 0 read-only audit")
