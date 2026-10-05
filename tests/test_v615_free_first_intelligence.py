from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import v615_auto_thesis_engine as eng
import system_status_center as status

doc=eng.build()
assert doc["mode"]=="evidence_grounded_autofill_draft"
assert doc["external_requests"]==0
assert isinstance(doc["symbols"],dict)
for row in doc["symbols"].values():
    assert "evidence_hash" in row
    assert "guardrail" in row
    assert row["guardrail"].startswith("Evidence-grounded")
    assert "sources" in row

guard=status.build_resource_guard({"quant-dashboard":{},"wxc-bot":{}},{})
assert guard["free_first"] is True
assert guard["billing_meter"] is False
assert guard["mode"] in {"normal","watch","conserve"}

js=(ROOT/"docs"/"assets"/"stock-watchlist.js").read_text(encoding="utf-8")
pi=(ROOT/"docs"/"assets"/"product-intelligence.js").read_text(encoding="utf-8")
assert "auto_thesis_drafts.json" in js
assert "系统自动补充 · 官方/事件证据草稿" in js
assert "opportunityScore" in pi
assert "priority:100" in pi and "sort((a,b)=>(b.priority||0)-(a.priority||0))" in pi
assert "免费额度守门" in pi
print("PASS V6.15 free-first opportunity/action/thesis foundation")
