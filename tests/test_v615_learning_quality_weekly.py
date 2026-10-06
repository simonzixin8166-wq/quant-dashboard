from pathlib import Path
import importlib.util
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("lqw",ROOT/"scripts"/"learning_quality_weekly.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
current={"learning_health":{"score":80},"engine_quality":{
"market":{"validation_state":"forward_unproven","feedback_state":"research_priority_only","forward_mature_20":0},
"fundamental":{"validation_state":"descriptive_outcomes_maturing","feedback_state":"thesis_review_plus_outcome_context","linked_direct_events":6},
"event":{"validation_state":"descriptive_context_only","feedback_state":"hypothesis_only","review_samples":5},
"options":{"validation_state":"state_observations_started","feedback_state":"risk_monitoring_plus_outcomes","state_observations":3},
"decision":{"validation_state":"persisted_samples_present","feedback_state":"human_attribution_required","persisted_operator_decisions":4}}}
previous={"snapshot":{"options":{"numeric":{"state_observations":1}}}}
out=m.build(current,previous,datetime(2026,10,6,tzinfo=timezone.utc))
assert out["week"]=="2026-W41"
assert any(x["engine"]=="options" and x["numeric_deltas"]["state_observations"]==2 for x in out["changes_since_previous_report"])
assert any(x["engine"]=="market" for x in out["attention"])
assert "Forward/Outcome Learning" in out["principle"]
print("PASS weekly learning quality report")
