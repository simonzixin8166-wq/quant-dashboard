import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v616_readiness_gate import build

spec={"readiness_spec_version":"1.0","requirements":{
 "statistical_controls_required":["positive_control","repeated_negative_control","leakage_canary"],
 "production_boundary_clean_workflow_runs_min":5,
 "point_in_time_mature_20_events_min":12,
 "point_in_time_mature_60_events_min":6,
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
for i in range(12):
    rid="r1" if i<6 else "r2"
    events.append({
      "event_id":f"e{i}","rule_id":rid,"scoreable":True,"point_in_time_status":"eligible",
      "scores":{"20":{"raw_return":0.01},"60":{"raw_return":0.02} if i<6 else None}
    })
event_doc={"counts":{"conservation_ok":True},"events":events}
source={"source_window_reported_total":3,"records":[1,2,3]}
controls={"all_pass":True,"controls":{
 "positive_control":{"pass":True},"repeated_negative_control":{"pass":True},"leakage_canary":{"pass":True}
}}
boundary={"records":[]}
for i in range(5):
    for step in ("a","b"):
        boundary["records"].append({"workflow_run_id":str(i),"step":step,"production_boundary_unchanged":True,"research_only_worktree":True})
components={"counts":{"missing_code_hashes":0,"missing_required_artifact_hashes":0}}
out=build(spec,event_doc,families,source,controls,boundary,components)
assert out["ready_for_v616"] is True
assert out["promotion_pass_required"] is False

event_doc2={"counts":{"conservation_ok":True},"events":events[:5]}
out2=build(spec,event_doc2,families,source,controls,boundary,components)
assert out2["ready_for_v616"] is False
assert "point_in_time_mature_20_events" in out2["blockers"]
print("PASS V6.15.8c independent V6.16 Readiness Gate")
