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
    return {"status":"available","rows":10,"http_status":200,"content_type":"text/csv","response_bytes":100,"response_prefix":"Date,Open","symbol_mapping":sym.lower()+".us"}
out=build(events,core={},cache={"INTC":"dummy"},probe_fn=available)
assert out["counts"]["symbols"]==1
assert out["counts"]["events"]==2
assert out["control_symbol"]=="AAPL"
assert out["control_probe"]["status"]=="available"
row=out["symbols"][0]
assert row["symbol"]=="INTC"
assert row["classification"]=="universe_gap"
assert row["upstream_stooq_probe"]["http_status"]==200

def access_failed(sym):
    return {"status":"access_failure","http_status":403,"error":"Forbidden","symbol_mapping":sym.lower()+".us"}
out2=build(events,core={},cache={"INTC":"dummy"},probe_fn=access_failed)
assert out2["symbols"][0]["classification"]=="access_failure"
assert out2["control_probe"]["status"]=="access_failure"

def no_rows(sym):
    if sym=="AAPL": return available(sym)
    return {"status":"no_valid_rows","rows":0,"http_status":200,"content_type":"text/plain","response_bytes":5,"response_prefix":"No data","symbol_mapping":sym.lower()+".us"}
out3=build(events,core={},cache={"INTC":"dummy"},probe_fn=no_rows)
assert out3["symbols"][0]["classification"]=="symbol_mapping_or_true_no_coverage_unresolved"

out4=build(events,core={"INTC":"dummy"},cache={"INTC":"dummy"},probe_fn=available)
assert out4["symbols"][0]["classification"]=="universe_gap_or_local_selection_bug"
print("PASS V6.15.8d STOOQ controlled-access coverage audit")
