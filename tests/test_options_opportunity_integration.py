from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
stock=(ROOT/"docs"/"assets"/"stock-watchlist.js").read_text(encoding="utf-8")
assistant=(ROOT/"docs"/"assets"/"investment-assistant.js").read_text(encoding="utf-8")
options=(ROOT/"docs"/"assets"/"options-v2.js").read_text(encoding="utf-8")
context=(ROOT/"scripts"/"options_opportunity_context.py").read_text(encoding="utf-8")

# Discovery may use system evidence, but must preserve the distinction from a
# manually confirmed Thesis.
for token in ["hasAutoEvidence","hasResearchBasis","researchBasisType"]:
    assert token in stock
assert "manual_thesis" in stock and "auto_evidence" in stock

# The assistant may send research basis into the live-chain scanner, but only
# for a governed scan context produced by the backend artifact.
assert "ranked_scan_order" in assistant
assert "scan_context_ready" in assistant
assert "researchBasis:x.hasResearchBasis" in assistant
assert "allowedModes:ctx.research_modes" in assistant

# Live chain screening accepts manual Thesis, auto evidence, or QQQ index case
# only as research gates. Every emitted strategy-shaped result remains WATCH
# and researchOnly.
assert "hasThesis||researchBasis||symbol==='QQQ'" in options
assert "researchBasisType" in options
for kind in ["SELL PUT WATCH","LEAPS WATCH","BUY CALL WATCH"]:
    assert kind in options
assert options.count("researchOnly:true") >= 3

# Backend context never emits a trade action or Production effect.
assert '"trade_action":None' in context
assert '"production_effect":"none"' in context
assert "SELL_PUT_SCREEN" in context and "LEAPS_SCREEN" in context

print("PASS option opportunity integration / auto-evidence research only / no production promotion")
