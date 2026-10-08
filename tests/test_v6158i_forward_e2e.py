import json,sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_rule_registry import build as build_registry
from v615_rule_family import build as build_families
from v615_event_score import adapt
from v615_persistent_source_store import migrate_sources

spec=json.loads((ROOT/"research/specs/evaluation_spec.json").read_text())
definition=json.loads((ROOT/"research/specs/rule_family_definition.json").read_text())

source_id="synthetic-forward-source"
op={"symbols":["ABC"],"entry_below":100.0,"conditions":["pullback"],"actions":["buy"],"attribution":"author_plan"}
forward_record={"id":source_id,"source":"wenxuecity","source_kind":"blog","author":"forward-author","published_at":"2026-10-06","title":"synthetic forward canary","url":"https://example.invalid/forward","operations":[op]}
source={
 "records":[forward_record],
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
seed_record={"id":"seed-old","source":"feed","source_kind":"post","author":"seed","published_at":"2026-10-04T00:00:00+00:00","title":"seed","url":"https://example.invalid/seed","operations":[]}
seed_store=migrate_sources({"counts":{"records":1},"records":[seed_record]},None,now="2026-10-04T00:00:00+00:00",full_records=[seed_record],spec=spec)
source_store=migrate_sources({"counts":{"records":2},"records":[seed_record,forward_record]},seed_store,now="2026-10-06T00:00:00+00:00",full_records=[seed_record,forward_record],spec=spec)
forward_row=[x for x in source_store["records"] if x["source_key"]==source_id][0]
assert forward_row["admission_class"]=="genuine_forward"
assert forward_row["ingest_type"]=="live_ingest"
assert forward_row["effective_forward_eligible"] is True

registry=build_registry(reading,source,{},now="2026-10-06T00:00:01+00:00",source_store=source_store)
assert registry["counts"]["active"]==1
assert registry["rules"][0]["effective_forward_eligible"] is True
families=build_families(registry,spec,definition,{},now="2026-10-06T00:00:02+00:00")
assert families["counts"]["active_families"]==1
rule_id=registry["rules"][0]["rule_id"]
direction=[x for x in families["assignments"] if x["rule_id"]==rule_id and x["active"]][0]["family_key"]["direction"]
assert direction=="bullish"
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
print("PASS Spec 1.7 real migrate_sources -> registry -> family -> EventScore canary")


# Intraday leakage canary: source first seen after the baseline session open must fail closed.
late_store={"records":[{
 "source_key":source_id,"first_fetched_at":"2026-10-07T14:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "ingest_type":"live_ingest","admission_class":"genuine_forward","record":{"id":source_id}
}]}
late=adapt(validation,registry,histories,spec,late_store,families)
late_row=late["events"][0]
assert late_row["point_in_time_status"]=="historical_pre_ingest"
assert late_row["scoreable"] is False
assert late_row["primary_exclusion_reason"]=="non_point_in_time_source"
print("PASS Spec 1.7 intraday forward leakage canary")


# EventScore independently rejects a forged/non-genuine source even if Guard is never called.
forged_store={"records":[{
 "source_key":source_id,"first_fetched_at":"2026-10-06T00:00:00+00:00",
 "first_fetched_at_origin":"source_store_first_observation",
 "ingest_type":"live_ingest","admission_class":"rekeyed_duplicate","record":{"id":source_id}
}]}
forged=adapt(validation,registry,histories,spec,forged_store,families)
fr=forged["events"][0]
assert fr["point_in_time_status"]=="source_not_genuine_forward"
assert fr["scoreable"] is False
assert fr["primary_exclusion_reason"]=="non_point_in_time_source"
print("PASS Spec 1.7 EventScore independently enforces source admission")
