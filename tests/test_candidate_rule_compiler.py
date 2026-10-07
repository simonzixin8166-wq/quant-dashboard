import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.candidate_rule_compiler import build

def memory(cid, machine=True, sid="s1"):
    return {
      "records":[{
        "source_id":sid,"author":"tester","source":"wenxuecity","source_kind":"blog",
        "published_at":"2026-10-01","title":"test","url":"https://example.test/x",
        "symbols":["AAA"],"content_quality":"Q2",
        "propositions":[{
          "proposition_id":"p1","kind":"candidate_rule",
          "evidence":{"candidate_rule":{
            "symbols":["AAA"],
            "conditions":[{"condition_id":cid,"machine_ready":machine}],
            "state_hint":"EARLY_ENTRY","raw_evidence":["source text"]
          }}
        }]
      }]
    }

def store(admission="backfill",confidence="high",sid="s1"):
    return {"records":[{"source_key":"k1","admission_class":admission,"timestamp_confidence":confidence,"record":{"id":sid}}]}

# Machine-reproducible historical candidate: replayable, never Forward/production.
r=build(memory("price_above_ma50"),store("backfill"))
c=r["candidates"][0]
assert c["reproducibility_status"]=="machine_ready_shadow"
assert c["historical_replay_eligible"] is True
assert c["forward_observation_eligible"] is False
assert c["production_eligible"] is False
assert c["promotion_eligible"] is False

# Genuine-forward + high timestamp can be observed prospectively, still not production.
r=build(memory("price_above_ma50"),store("genuine_forward","high"))
c=r["candidates"][0]
assert c["forward_observation_eligible"] is True
assert c["production_eligible"] is False

# Undefined TCDS must remain unresolved; formula is never invented.
r=build(memory("tcds_cross_zero",False),store("genuine_forward","high"))
c=r["candidates"][0]
assert c["reproducibility_status"]=="blocked_needs_definition"
assert c["forward_observation_eligible"] is False
assert c["conditions"][0]["expression"] is None
assert "TCDS formula" in c["unresolved_inputs"][0]["reason"]

# PPO is partial/blocked unless definition is verified.
r=build(memory("ppo_above_signal",False),store("backfill"))
assert r["candidates"][0]["forward_observation_eligible"] is False
assert r["counts"]["production_eligible"]==0

print("PASS candidate rule compiler guardrails")
