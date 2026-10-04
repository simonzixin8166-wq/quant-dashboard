import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_event_score import reconcile_history,entry_type,adapt

idx=pd.to_datetime(["2026-01-01","2026-01-02","2026-01-03"])
stooq=pd.DataFrame({"open":[100,101,102],"high":[101,102,103],"low":[99,100,101],"close":[100,101,102]},index=idx)
cache=stooq.copy()
df,meta=reconcile_history(stooq,cache)
assert meta["status"]=="ok"
bad=cache.copy();bad.loc[idx[1],"close"]=150
_,meta2=reconcile_history(stooq,bad)
assert meta2["status"]=="conflict"

assert entry_type({"baseline_kind":"entry_1","operation":{"conditions":["breakout above resistance"]}})=="breakout"
assert entry_type({"baseline_kind":"entry_1","operation":{"conditions":[]}})=="unknown"
assert entry_type({"baseline_kind":"entry_below","operation":{}})=="conditional"

validation={"events":[{
 "event_id":"s1:0:ABC:0","author":"a","symbol":"ABC","published_at":"2026-01-01",
 "baseline_date":"2026-01-02","baseline_kind":"entry_1","triggered":True,
 "operation":{"conditions":[],"actions":["buy"]},"alignment":{"direction":"bullish","5":"aligned"},
 "outcomes":{"5":{"return":0.1,"benchmark_return":0.1,"excess_vs_qqq":0.0,"mae":-0.02,"mfe":0.12}}
}]}
registry={"legacy_mapping":[{"source_id":"s1","operation_index":0,"rule_id":"r1"}]}
hist={"ABC":{"df":stooq,"meta":{"status":"ok","source":"stooq_archive","price_series_hash":"x"}}}
out=adapt(validation,registry,hist,{"spec_version":"1.0"})
assert out["events"][0]["scoreable"] is False
assert "unknown_entry_semantics" in out["events"][0]["exclusion_reasons"]

# Negative test: source conflict must keep event unscored.
validation["events"][0]["baseline_kind"]="entry_below"
hist["ABC"]["meta"]["status"]="conflict"
out2=adapt(validation,registry,hist,{"spec_version":"1.0"})
assert out2["events"][0]["scoreable"] is False
assert "price_source_conflict" in out2["events"][0]["exclusion_reasons"]
print("PASS V6.15.2 EventScore adapter / entry semantics / price consistency")
