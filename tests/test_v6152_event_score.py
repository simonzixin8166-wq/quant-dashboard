import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_event_score import reconcile_history,entry_type,adapt,historical_unconditional_metrics

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
 "price_provenance":{"price_source":"stooq_archive","adjustment_basis":"stooq_archive_native_series","baseline_source":"stooq_archive","horizon_source":"stooq_archive","same_source":True},
 "outcomes":{"5":{"date":"2026-01-09","return":0.1,"benchmark_return":0.1,"excess_vs_qqq":0.0,"mae":-0.02,"mfe":0.12}}
}]}
registry={"legacy_mapping":[{"source_id":"s1","operation_index":0,"rule_id":"r1"}]}
hist={"ABC":{"df":stooq,"meta":{"status":"ok","source":"stooq_archive","price_series_hash":"x"}}}
source_store={"records":[{"source_key":"s1","first_fetched_at":"2025-12-01T00:00:00Z","ingest_type":"test","published_at_semantics":"source_archive_publication_date","timestamp_confidence":"high","snapshot_hash":"h","record":{"id":"s1"}}]}
out=adapt(validation,registry,hist,{"spec_version":"1.0"},source_store)
assert out["events"][0]["scoreable"] is False
assert "unknown_entry_semantics" in out["events"][0]["exclusion_reasons"]
assert out["events"][0]["scores"]["5"]["horizon_end_date"]=="2026-01-09"

# Negative test: source conflict must keep event unscored.
validation["events"][0]["baseline_kind"]="entry_below"
hist["ABC"]["meta"]["status"]="conflict"
out2=adapt(validation,registry,hist,{"spec_version":"1.0"},source_store)
assert out2["events"][0]["scoreable"] is False
assert "price_source_conflict" in out2["events"][0]["exclusion_reasons"]
print("PASS V6.15.2 EventScore adapter / entry semantics / price consistency")


# Every non-scoreable event must have exactly one primary exclusion reason.
assert out["counts"]["conservation_ok"] is True
assert out["counts"]["events"] == out["counts"]["scoreable"] + sum(out["counts"]["primary_exclusion"].values())
assert out["events"][0]["primary_exclusion_reason"]=="unknown_entry_semantics"
assert out2["events"][0]["primary_exclusion_reason"]=="price_source_conflict"

# Cache-only data must never silently produce scoreable=false with no reason.
hist_cache={"ABC":{"df":stooq,"meta":{"status":"cache_only_unscored","source":"cache","price_series_hash":"x"}}}
out3=adapt(validation,registry,hist_cache,{"spec_version":"1.0"},source_store)
assert out3["events"][0]["scoreable"] is False
assert out3["events"][0]["primary_exclusion_reason"]=="cache_only_unscored"

# Prior-only baseline can never consume a forward path that reaches the decision date.
idx2=pd.date_range("2025-01-01",periods=90,freq="B")
base=pd.DataFrame({
 "open":[100.0]*90,"high":[101.0]*90,"low":[99.0]*90,"close":[100.0]*90
},index=idx2)
decision=idx2[80]
m1=historical_unconditional_metrics(base,decision,20,"bullish")
base2=base.copy()
# Mutating decision-date and later values must not change the historical baseline.
base2.loc[base2.index>=decision,["open","high","low","close"]]=9999.0
m2=historical_unconditional_metrics(base2,decision,20,"bullish")
assert m1==m2


# Family structural direction overrides permissive legacy alignment for eligibility.
mixed_validation={"events":[{
 "event_id":"s1:0:ABC:0","author":"a","symbol":"ABC","published_at":"2026-01-01",
 "baseline_date":"2026-01-02","baseline_kind":"entry_below","triggered":True,
 "operation":{"conditions":[],"actions":["planned_buy","planned_sell"]},
 "alignment":{"direction":"bullish","5":"aligned"},
 "price_provenance":{"price_source":"stooq_archive","adjustment_basis":"stooq_archive_native_series","baseline_source":"stooq_archive","horizon_source":"stooq_archive","same_source":True},
 "outcomes":{"5":{"date":"2026-01-09","return":0.1,"benchmark_return":0.1,"excess_vs_qqq":0.0,"mae":-0.02,"mfe":0.12}}
}]}
mixed_spec={"spec_version":"1.4","definitions":{"rule_family_definition_hash":"h"}}
mixed_families={"assignments":[{
 "rule_id":"r1","family_id":"f1","definition_hash":"h","active":True,
 "family_key":{"direction":"mixed_direction"}
}]}
mixed_hist={"ABC":{"df":stooq,"meta":{"status":"ok","source":"stooq_archive","price_series_hash":"x"}}}
mixed_out=adapt(mixed_validation,registry,mixed_hist,mixed_spec,source_store,mixed_families)
mr=mixed_out["events"][0]
assert mr["rule_structural_direction"]=="mixed_direction"
assert mr["scoreable"] is False
assert "unsupported_direction" in mr["exclusion_reasons"]
assert mr["primary_exclusion_reason"]=="unsupported_direction"
print("PASS V6.15.8h mixed-direction family fails closed despite bullish legacy label")


# Forward-path positive control: a post-ingest, known-entry, same-source event can become scoreable.
forward_validation={"events":[{
 "event_id":"s1:0:ABC:forward","author":"a","symbol":"ABC","published_at":"2026-01-01",
 "baseline_date":"2026-01-02","baseline_kind":"entry_below","triggered":True,
 "operation":{"conditions":[],"actions":["buy"]},"alignment":{"direction":"bullish","5":"aligned"},
 "price_provenance":{"price_source":"stooq_archive","adjustment_basis":"stooq_archive_native_series","baseline_source":"stooq_archive","horizon_source":"stooq_archive","same_source":True},
 "outcomes":{"5":{"date":"2026-01-09","return":0.1,"benchmark_return":0.1,"excess_vs_qqq":0.0,"mae":-0.02,"mfe":0.12}}
}]}
forward_families={"assignments":[{
 "rule_id":"r1","family_id":"f1","definition_hash":"h","active":True,"family_key":{"direction":"bullish"}
}]}
forward_spec={"spec_version":"1.5","definitions":{"rule_family_definition_hash":"h"}}
forward_store={"records":[{"source_key":"s1","first_fetched_at":"2025-12-01T00:00:00Z","record":{"id":"s1"}}]}
forward=adapt(forward_validation,registry,{"ABC":{"df":stooq,"meta":{"status":"ok","source":"stooq_archive","price_source":"stooq_archive","adjustment_basis":"stooq_archive_native_series","price_series_hash":"x"}}},forward_spec,forward_store,forward_families)
assert forward["events"][0]["scoreable"] is True
assert forward["events"][0]["point_in_time_status"]=="eligible"
assert forward["events"][0]["scoring_engine_version"].startswith("event_score@")
print("PASS V6.15.8i forward EventScore positive path / explicit price provenance")
