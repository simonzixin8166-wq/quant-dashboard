import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.candidate_parameter_queue import build

reg={
 "candidates":[
  {
   "candidate_id":"c1","family_signature":"f1","method_family":"trend_confirmation","state_role":"trigger",
   "scope":{"symbols":["AMZN"]},
   "source":{"author":"A","title":"TCDS idea","published_at":"2026-10-01","url":"u1"},
   "unresolved_inputs":[
    {"condition_id":"tcds_cross_zero","reason":"TCDS formula/parameters not defined in source"},
    {"condition_id":"ppo_above_signal","reason":"PPO periods/definition not verified"},
   ]
  },
  {
   "candidate_id":"c2","family_signature":"f2","method_family":"trend_confirmation","state_role":"trigger",
   "scope":{"symbols":["LITE"]},
   "source":{"author":"B","title":"Supertrend","published_at":"2026-10-02","url":"u2"},
   "unresolved_inputs":[{"condition_id":"supertrend_bullish","reason":"Supertrend ATR period/multiplier not verified"}]
  },
  {
   "candidate_id":"c3","family_signature":"f3","method_family":"trend_confirmation","state_role":"risk",
   "scope":{"symbols":["AMZN"]},"source":{"author":"A","title":"temporal","url":"u3"},
   "unresolved_inputs":[{"condition_id":"temporal_sequence_window","reason":"window undefined"}]
  }
 ]
}
out=build(reg)
assert out["state"]=="waiting_for_source_definitions"
assert out["counts"]["queue_items"]==3
assert out["counts"]["candidates_affected"]==2
assert out["counts"]["conditions_waiting"]==3
assert out["by_condition"]["tcds_cross_zero"]==1
assert all(x["can_use_default_parameters"] is False for x in out["items"])
assert all(x["production_eligible"] is False for x in out["items"])
assert not any(x["condition_id"]=="temporal_sequence_window" for x in out["items"])

empty=build({"candidates":[]})
assert empty["state"]=="all_parameterized_conditions_resolved"
assert empty["counts"]["queue_items"]==0
assert empty["production_effect"]=="none"
assert empty["promotion_effect"]=="none"

print("PASS parameter definition queue / source-defined-only guardrails")
