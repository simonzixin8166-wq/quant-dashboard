import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/"scripts"))
from autonomous_signal_governance import build

closed={"results":[{"family_id":"f1","passed":False,"production_effect":"none"}]}
evidence={"promotion":{"production_effect":"none"}}
out=build(closed,evidence)
assert out["learned_production_effect"]=="none"
assert out["promoted_families"]==[]
assert out["formal_app_version"]=="6.9.0"
assert out["decision_authority"]=="today_cockpit"
assert out["policy"]["automatic_trading"] is False

# Even a statistically passed family is fail-closed unless BOTH artifacts
# explicitly authorize an active production effect.
shadow={"results":[{"family_id":"f1","passed":True,"production_effect":"none"}]}
assert build(shadow,{"promotion":{"production_effect":"active"}})["learned_production_effect"]=="none"

active={"results":[{"family_id":"f1","passed":True,"production_effect":"active","member_rule_ids":["r1"]}]}
out=build(active,{"promotion":{"production_effect":"active"}})
assert out["learned_production_effect"]=="active"
assert out["promoted_families"][0]["family_id"]=="f1"
print("PASS governed autonomous signal bridge")
