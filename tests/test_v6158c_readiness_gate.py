import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v616_readiness_gate import build

def score(day,h,val):
    return {"raw_return":val,"horizon_end_date":(pd.Timestamp(day)+pd.tseries.offsets.BDay(h)).date().isoformat()}

spec={"readiness_spec_version":"1.1","requirements":{
 "statistical_controls_required":["positive_control","repeated_negative_control","leakage_canary"],
 "production_boundary_clean_workflow_runs_min":5,
 "production_boundary_clean_span_days_min":14,
 "point_in_time_mature_20_effective_units_min":12,
 "point_in_time_mature_60_effective_units_min":6,
 "families_with_mature_20_min":2,
 "families_with_mature_60_min":1,
 "unresolved_integrity_blockers_max":0,
 "promotion_pass_required":False
}}
families={"definition_hash":"h","assignments":[
 {"rule_id":"r1","family_id":"f1","definition_hash":"h","active":True},
 {"rule_id":"r2","family_id":"f2","definition_hash":"h","active":True}
]}
events=[]
symbols=["AAA","BBB","CCC"]
# f1: two pairwise non-overlapping 60-session clusters.
for day in ["2026-01-05","2026-04-13"]:
    for sym in symbols:
        events.append({"event_id":f"r1-{day}-{sym}","rule_id":"r1","symbol":sym,"baseline_date":day,
          "scoreable":True,"point_in_time_status":"eligible",
          "scores":{"20":score(day,20,0.01),"60":score(day,60,0.02)}})
# f2: two extra non-overlapping 20-session clusters, separated from f1's 20d windows.
for day in ["2026-03-02","2026-06-15"]:
    for sym in symbols:
        events.append({"event_id":f"r2-{day}-{sym}","rule_id":"r2","symbol":sym,"baseline_date":day,
          "scoreable":True,"point_in_time_status":"eligible",
          "scores":{"20":score(day,20,0.01),"60":None}})
event_doc={"counts":{"conservation_ok":True},"events":events}
source={"source_window_reported_total":3,"records":[1,2,3]}
controls={"all_pass":True,"controls":{
 "positive_control":{"pass":True},"repeated_negative_control":{"pass":True},"leakage_canary":{"pass":True}
}}
boundary={"records":[]}
days=["2026-10-01","2026-10-05","2026-10-09","2026-10-13","2026-10-17"]
for i,day in enumerate(days):
    for step in ("a","b"):
        boundary["records"].append({"workflow_run_id":str(i),"step":step,
          "completed_at":day+"T12:00:00+00:00",
          "production_boundary_unchanged":True,"research_only_worktree":True,"evidence_lock_unchanged":True})
components={"counts":{"missing_code_hashes":0,"missing_required_artifact_hashes":0}}
out=build(spec,event_doc,families,source,controls,boundary,components)
assert out["ready_for_v616"] is True
assert out["promotion_pass_required"] is False
assert out["observed"]["mature_20_effective_units"]==12
assert out["observed"]["mature_60_effective_units"]==6
assert out["observed"]["clean_boundary_span_days"]>=14

# Overlapping 60d events cannot inflate readiness merely by crossing calendar buckets.
overlap=list(events)
for sym in symbols:
    overlap.append({"event_id":f"overlap-{sym}","rule_id":"r1","symbol":sym,"baseline_date":"2026-01-12",
      "scoreable":True,"point_in_time_status":"eligible",
      "scores":{"20":score("2026-01-12",20,0.01),"60":score("2026-01-12",60,0.02)}})
out_overlap=build(spec,{"counts":{"conservation_ok":True},"events":overlap},families,source,controls,boundary,components)
assert out_overlap["observed"]["mature_60_effective_units"]==6

event_doc2={"counts":{"conservation_ok":True},"events":events[:5]}
out2=build(spec,event_doc2,families,source,controls,boundary,components)
assert out2["ready_for_v616"] is False
assert "point_in_time_mature_20_effective_units" in out2["blockers"]

short_boundary={"records":[dict(x,completed_at="2026-10-01T12:00:00+00:00") for x in boundary["records"]]}
out3=build(spec,event_doc,families,source,controls,short_boundary,components)
assert out3["ready_for_v616"] is False
assert "production_boundary_clean_span" in out3["blockers"]
print("PASS V6.15.8e Readiness overlap-connected units / minimum run span")
