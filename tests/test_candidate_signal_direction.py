import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.candidate_signal_direction import govern

bull=govern({"conditions":[
 {"condition_id":"price_above_ma50","machine_ready":True},
 {"condition_id":"ma50_hold_two_sessions","machine_ready":True},
]})
assert bull["state"]=="direction_governed"
assert bull["expected_direction"]=="bullish"
assert bull["trade_action"] is None

bear=govern({"conditions":[{"condition_id":"price_below_ma200","machine_ready":True}]})
assert bear["expected_direction"]=="bearish"

mixed=govern({"conditions":[
 {"condition_id":"price_above_ma50","machine_ready":True},
 {"condition_id":"price_below_ma20","machine_ready":True},
]})
assert mixed["state"]=="direction_conflict"
assert mixed["expected_direction"] is None

unknown=govern({"conditions":[{"condition_id":"tcds_cross_zero","machine_ready":False}]})
assert unknown["state"]=="direction_unresolved"
assert unknown["expected_direction"] is None
assert unknown["production_effect"]=="none"
assert unknown["promotion_effect"]=="none"
print("PASS candidate signal direction governance / no trade-action inference")
