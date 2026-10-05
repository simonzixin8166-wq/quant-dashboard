import json,sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_rule_registry import build as build_registry
from v615_rule_family import build as build_families
from v615_event_score import adapt

spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
definition=json.loads((ROOT/"research/specs/rule_family_definition.json").read_text())

source_id="synthetic-forward-source"
op={"symbols":["ABC"],"entry_below":100.0,"conditions":["pullback"],"actions":["buy"],"attribution":"author_plan"}
source={
 "records":[{"id":source_id,"operations":[op]}],
 "operation_cases":[{"id":source_id,"operations":[op]}],
}
reading={"version":"synthetic-e2e","records":[{
 "source_id":source_id,"author":"forward-author","published_at":"2026-10-06",
 "title":"synthetic forward canary","url":"https://example.invalid/forward",
 "symbols":["ABC"],"extractor_input_hash":"synthetic-input","extractor_input_scope":"test-only",
 "propositions":[{
   "kind":"testable_rule",
   "evidence":{
     "rule":{"fields":{"entry_below":100.0},"conditions":["pullback"],"actions":["buy"]},
     "method_candidates":["趋势确认"],"attribution":"author_plan","operation_index":0
   }
 }]
}]}

registry=build_registry(reading,source,{},now="2026-10-06T00:00:00+00:00")
assert registry["counts"]["active"]==1
families=build_families(registry,spec,definition,{},now="2026-10-06T00:00:01+00:00")
assert families["counts"]["active_families"]==1
rule_id=registry["rules"][0]["rule_id"]
direction=[x for x in families["assignments"] if x["rule_id"]==rule_id and x["active"]][0]["family_key"]["direction"]
assert direction=="bullish"

idx=pd.date_range("2026-06-01",periods=100,freq="B")
df=pd.DataFrame({
 "open":[100.0]*100,"high":[101.0]*100,"low":[99.0]*100,"close":[100.0]*100
},index=idx)
baseline="2026-10-07"
validation={"events":[{
 "event_id":f"{source_id}:0:ABC:0","author":"forward-author","symbol":"ABC",
 "published_at":"2026-10-06","baseline_date":baseline,"baseline_kind":"entry_below",
 "triggered":True,"operation":{"conditions":["pullback"],"actions":["buy"]},
 "alignment":{"direction":"bullish","5":"aligned"},
 "price_provenance":{
   "price_source":"stooq_archive","adjustment_basis":"stooq_archive_native_series",
   "baseline_source":"stooq_archive","horizon_source":"stooq_archive","same_source":True
 },
 "outcomes":{"5":{
   "date":"2026-10-14","return":0.01,"benchmark_return":0.0,"excess_vs_qqq":0.01,
   "mae":-0.01,"mfe":0.02
 }}
}]}
source_store={"records":[{
 "source_key":source_id,"first_fetched_at":"2026-10-06T00:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "ingest_type":"live_ingest","published_at_semantics":"upstream_published_at_unverified",
 "timestamp_confidence":"unverified","snapshot_hash":"synthetic","record":{"id":source_id}
}]}
histories={"ABC":{"df":df,"meta":{
 "status":"ok","source":"stooq_archive","price_source":"stooq_archive",
 "adjustment_basis":"stooq_archive_native_series","same_source_only":True,
 "price_series_hash":"synthetic"
}}}
out=adapt(validation,registry,histories,spec,source_store,families)
row=out["events"][0]
assert row["point_in_time_status"]=="eligible"
assert row["scoreable"] is True
assert row["primary_exclusion_reason"] is None
assert row["price_provenance"]["baseline_source"]==row["price_provenance"]["horizon_source"]=="stooq_archive"
assert row["scoring_engine_version"].startswith("event_score@")
print("PASS Spec 1.6 isolated forward source -> registry -> family -> EventScore canary")


# Intraday leakage canary: source first seen after the baseline session open must fail closed.
late_store={"records":[{
 "source_key":source_id,"first_fetched_at":"2026-10-07T14:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "ingest_type":"live_ingest","record":{"id":source_id}
}]}
late=adapt(validation,registry,histories,spec,late_store,families)
late_row=late["events"][0]
assert late_row["point_in_time_status"]=="historical_pre_ingest"
assert late_row["scoreable"] is False
assert late_row["primary_exclusion_reason"]=="non_point_in_time_source"
print("PASS Spec 1.6 intraday forward leakage canary")
