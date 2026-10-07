import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.candidate_rule_families import build

base={
 "family_signature":"family_x","method_family":"trend_confirmation","state_role":"trigger",
 "reproducibility_status":"machine_ready_shadow","forward_observation_eligible":False,
 "unresolved_inputs":[],"scope":{"symbols":["AAA"]},"source":{"author":"a"}
}
c1={**base,"candidate_id":"c1"}
c2={**base,"candidate_id":"c2","source":{"author":"b"}}
r=build({"candidates":[c1,c2]},{"candidates":[
 {"candidate_id":"c1","status":"replayed","raw_events":10,"effective_clusters":7},
 {"candidate_id":"c2","status":"replayed","raw_events":6,"effective_clusters":4},
]})
f=r["families"][0]
assert f["candidate_count"]==2
assert f["independent_authors"]==2
assert f["historical_raw_events"]==16
assert f["historical_effective_clusters"]==11
assert f["promotion_eligible"] is False
assert r["counts"]["production_eligible"]==0
print("PASS candidate rule family aggregation")
