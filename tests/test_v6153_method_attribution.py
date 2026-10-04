import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_method_attribution import build,normalize_methods,claim_semantics

p,s=normalize_methods(["仓位与加减仓","趋势确认"])
assert p=="趋势确认" and s==[]
p,s=normalize_methods(["Sell Put","趋势确认"])
assert p=="Sell Put" and s==["趋势确认"]

registry={"rules":[{"rule_id":"r1","method_candidates":["仓位与加减仓","趋势确认"],"normalized_rule":{"actions":["buy"],"fields":{"entry_1":10}}}]}
events={"events":[{"event_id":"e1","rule_id":"r1","scoreable":True,"spec_version":"1.0"}]}
reading={"records":[
 {"source_id":"s","source_kind":"blog","author":"a","propositions":[{"proposition_id":"p1","kind":"fact","text":"I bought","evidence":{"operation_index":0}}]},
 {"source_id":"o","source_kind":"sec","author":"issuer","propositions":[{"proposition_id":"p2","kind":"fact","text":"filed","evidence":{}}]}
]}
a,c=build(registry,events,reading)
assert a["events"][0]["primary_method"]=="趋势确认"
assert a["events"][0]["method_weight"]==1.0
assert a["events"][0]["operation_type"]=="buy_or_add"
claim={x["proposition_id"]:x for x in c["claims"]}
assert claim["p1"]["claim_type"]=="author_reported_action"
assert claim["p1"]["verification_status"]=="unverified"
assert claim["p2"]["claim_type"]=="verified_fact"
assert claim["p2"]["verification_status"]=="source_verified"
print("PASS V6.15.3 single attribution / operation type / claim semantics")
