import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ai",ROOT/"scripts"/"v615_author_intelligence.py")
ai=importlib.util.module_from_spec(spec);spec.loader.exec_module(ai)

source={"historical_learning":{"records":[
 {"author":"老李玩钱","quality":"Q2","historical_learning_eligible":True,"symbols":["NVDA"],"themes":["风险管理"],"macro_topics":[],"operations":[]},
 {"author":"Andrei Jikh","quality":"Q2","historical_learning_eligible":True,"symbols":[],"themes":[],"macro_topics":["利率/Fed"],"operations":[]},
]}}
rules={"rules":[
 {"rule_id":"legacy","author":"老李玩钱","forward_eligible":None},
 {"rule_id":"fwd","author":"Andrei Jikh","forward_eligible":True},
]}
families={"assignments":[{"rule_id":"fwd","family_id":"fam1","active":True}]}
events={"events":[
 {"rule_id":"legacy","author":"老李玩钱","point_in_time_status":"source_not_genuine_forward","scoreable":False,"maturity":{"20":True,"60":True}},
 {"rule_id":"fwd","author":"Andrei Jikh","point_in_time_status":"eligible","scoreable":True,"maturity":{"20":True,"60":False}},
]}
out=ai.build(source,rules,families,events,{"records":[]})
assert out["historical_learning"]["counts"]["records"]==2
assert out["historical_learning"]["non_gating"] is True
assert out["forward_evidence"]["counts"]["rules"]==1
assert out["forward_evidence"]["authors"][0]["author"]=="Andrei Jikh"
assert out["forward_evidence"]["authors"][0]["events"]==1
assert out["forward_evidence"]["authors"][0]["mature_20_events"]==1
assert all(x["author"]!="老李玩钱" for x in out["forward_evidence"]["authors"])
print("PASS V6.15 author intelligence historical/forward separation")
