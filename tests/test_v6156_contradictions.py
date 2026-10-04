import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from v615_contradiction_memory import detect,merge

registry={"rules":[
 {"rule_id":"r1","active":True,"author":"a","symbols":["ABC"],"source_id":"s1","normalized_rule":{"actions":["buy"]}},
 {"rule_id":"r2","active":True,"author":"a","symbols":["ABC"],"source_id":"s2","normalized_rule":{"actions":["sell"]}}
]}
claims={"claims":[
 {"proposition_id":"i1","source_id":"s1","original_kind":"invalidation","verification_status":"not_applicable"},
 {"proposition_id":"a1","contradiction_key":"k","stance":"up","verification_status":"unverified"},
 {"proposition_id":"o1","contradiction_key":"k","stance":"down","verification_status":"source_verified"}
]}
scores={"cards":[
 {"primary_methods":["M"],"evaluated_conclusion":"supportive"},
 {"primary_methods":["M"],"evaluated_conclusion":"challenging"}
]}
rows=detect(registry,claims,scores)
types={x["type"] for x in rows}
assert {"same_author_conflict","rule_invalidation_present","author_official_conflict","method_conclusion_conflict"}<=types
m1=merge(rows,now="t1");m2=merge(rows,m1,now="t2")
assert len(m1["records"])==len(m2["records"])
print("PASS V6.15.6 four contradiction classes / append-only memory")
