from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("sa",ROOT/"scripts"/"server_action_engine.py")
sa=importlib.util.module_from_spec(spec);spec.loader.exec_module(sa)

def p(**kw):
    base={"symbol":"TEST","opt_type":"put","strike":100,"expiry":"2099-12-31","status":"open"}
    base.update(kw);return base

q={"underlyingPrice":[120],"bid":[1],"ask":[1.1],"mid":[1.05],"delta":[-.1],"updated":[4102444800]}
r=sa.risk_for(p(),q,[])
assert r["level"]=="l1"
r2=sa.risk_for(p(expiry="2000-01-01"),q,[])
assert r2["level"]=="l3"
r3=sa.risk_for(p(),None,[])
assert r3["level"]=="unknown"
assert sa.occ_symbol(p(expiry="2026-12-18",strike=65))=="TEST261218P00065000"

src=(ROOT/"scripts"/"server_action_engine.py").read_text(encoding="utf-8")
assert "sanitized public summary only" in src
assert "MYALPHA_TG_BOT_TOKEN" in src
assert "cannot_judge" in src
assert "symbols/accounts/private position details are never written here" in src
print("PASS V6.15 server action engine")
