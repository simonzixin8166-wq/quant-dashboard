import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from source_reading_memory import extractor_input_hash,record_memory
from v615_rule_registry import build

row={
 "id":"s1","url":"u","title":"title","excerpt":"excerpt","source":"x","source_kind":"blog",
 "author":"a","published_at":"2026-01-01","symbols":["ABC"],"topics":["趋势确认"],
 "operations":[{"attribution":"author_action","symbols":["ABC"],"actions":["buy"],"conditions":["breakout"]}],
 "portfolio_rules":[],"lessons":[]
}
h=extractor_input_hash(row)
assert h==record_memory(row)["extractor_input_hash"]
unused=copy.deepcopy(row);unused["field_not_read_by_extractor"]="ignored"
assert extractor_input_hash(unused)==h
changed=copy.deepcopy(row);changed["excerpt"]="changed extractor input"
assert extractor_input_hash(changed)!=h

reading={"version":"x","records":[record_memory(row)]}
source={"records":[{"id":"s1","operations":row["operations"]}],"operation_cases":[]}
a=build(reading,source,{},now="t1")
rule=a["rules"][0]
assert rule["extractor_input_hash"]==h

changed_reading={"version":"y","records":[record_memory(changed)]}
b=build(changed_reading,source,a,now="t2")
same=[x for x in b["rules"] if x.get("rule_id")==rule["rule_id"]][0]
assert same["extractor_input_hash"]!=h
assert h in {x.get("extractor_input_hash") for x in same["extractor_input_revisions"]}
print("PASS V6.15.8d-2 exact extractor-input provenance revision")
