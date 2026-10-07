import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.candidate_evidence_promotion import build

spec={
 "spec_version":"1.7",
 "thresholds":{
  "independent_authors_min":3,
  "independent_time_clusters_min":6,
  "mature_60_effective_samples_min":20,
  "lift_ci95_lower_bound_gt":0,
  "mae_noninferiority_ci95_lower_bound_gte":0.0,
  "max_single_symbol_effective_unit_share":0.40,
 }
}
registry={"candidates":[
 {"candidate_id":"c1","family_signature":"f1","source_id":"s1","proposition_id":"p1","source":{"url":"u1"},"reproducibility_status":"machine_ready_shadow","signal_direction_governance":{"state":"direction_governed"}},
 {"candidate_id":"c2","family_signature":"f1","source_id":"s2","proposition_id":"p2","source":{"url":"u2"},"reproducibility_status":"machine_ready_shadow","signal_direction_governance":{"state":"direction_governed"}},
 {"candidate_id":"c3","family_signature":"f1","source_id":"s3","proposition_id":"p3","source":{"url":"u3"},"reproducibility_status":"machine_ready_shadow","signal_direction_governance":{"state":"direction_governed"}},
]}
events={"events":[
 {"event_id":"e1","family_signature":"f1","scoreable":True,"direction":"bullish","data_quality":{"status":"ok"},"price_provenance":{"same_source":True}},
 {"event_id":"e2","family_signature":"f1","scoreable":True,"direction":"bullish","data_quality":{"status":"ok"},"price_provenance":{"same_source":True}},
]}
good={"cards":[{
 "candidate_family_signature":"f1",
 "horizons":{"60":{
  "effective_n":20,"independent_time_clusters":6,"independent_authors":3,
  "lift_ci95":{"lower":0.01},"fdr":{"reject":True},
  "mae_noninferiority_ci95":{"lower":0.001},
  "single_symbol_effective_unit_share_max":0.35
 }}
}]}
out=build(good,registry,events,spec)
row=out["results"][0]
assert row["passed"] is True
assert row["decision_fusion_eligible"] is True
assert row["trade_action"] is None
assert row["production_eligible"] is False
assert out["production_effect"]=="none"
assert out["promotion_effect"]=="evidence_tier_only"

bad_registry={"candidates":[{**registry["candidates"][0],"signal_direction_governance":{"state":"direction_unresolved"}}]}
bad=build(good,bad_registry,events,spec)
assert bad["results"][0]["passed"] is False
assert "candidate_direction_governed" in bad["results"][0]["missing"]

empty=build({"cards":[]},{"candidates":[]},{"events":[]},spec)
assert empty["counts"]["passed"]==0
assert empty["production_effect"]=="none"
print("PASS Candidate Evidence Promotion Gate / evidence-only / no trade action")
