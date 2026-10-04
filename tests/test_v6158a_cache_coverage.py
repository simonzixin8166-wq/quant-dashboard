import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_cache_coverage_audit import build

events={"events":[
 {"event_id":"e1","rule_id":"r1","symbol":"INTC","author":"a","entry_type":"next_session","data_quality":{"status":"cache_only_unscored"}},
 {"event_id":"e2","rule_id":"r1","symbol":"INTC","author":"a","entry_type":"conditional","data_quality":{"status":"cache_only_unscored"}},
 {"event_id":"e3","rule_id":None,"symbol":"ZZZ","author":"a","entry_type":"next_session","data_quality":{"status":"cache_only_unscored"}}
]}
def available(sym):
    return {"status":"available","rows":10,"symbol_mapping":sym.lower()+".us"}
out=build(events,core={},cache={"INTC":"dummy"},probe_fn=available)
assert out["counts"]["symbols"]==1
assert out["counts"]["events"]==2
row=out["symbols"][0]
assert row["symbol"]=="INTC"
assert row["classification"]=="local_archive_provisioning_gap"

def failed(sym):
    return {"status":"temporary_probe_failure","error":"timeout","symbol_mapping":sym.lower()+".us"}
out2=build(events,core={},cache={"INTC":"dummy"},probe_fn=failed)
assert out2["symbols"][0]["classification"]=="temporary_probe_failure"

out3=build(events,core={"INTC":"dummy"},cache={"INTC":"dummy"},probe_fn=available)
assert out3["symbols"][0]["classification"]=="mapping_or_local_selection_bug"
print("PASS V6.15.8a cache-only STOOQ coverage audit classification")
