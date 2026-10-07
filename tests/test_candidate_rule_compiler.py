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

# First migration cycle is deliberately non-forward even for a genuine source.
r=build(memory("price_above_ma50"),store("genuine_forward","high"),prior={})
c=r["candidates"][0]
assert c["forward_observation_eligible"] is False
assert c["formation_mode"]=="migration_baseline"

# Once source-observation tracking exists, a new genuine-forward source may
# form a Forward-observation candidate only on its first compiler observation.
feature_prior={"source_observations":[{
  "source_id":"other","first_candidate_compiler_seen_at":"2026-10-01T00:00:00Z",
  "last_candidate_compiler_seen_at":"2026-10-01T00:00:00Z"
}]}
r=build(memory("price_above_ma50"),store("genuine_forward","high"),prior=feature_prior,now="2026-10-07T00:00:00Z")
c=r["candidates"][0]
assert c["forward_observation_eligible"] is True
assert c["formation_mode"]=="forward_initial"
assert c["production_eligible"] is False

# Hindsight guard: if a source was already observed without a candidate, a
# later extraction improvement must remain historical/retroactive.
empty={"records":[{
  "source_id":"s1","author":"tester","source":"wenxuecity","source_kind":"blog",
  "published_at":"2026-10-01","title":"test","url":"https://example.test/x",
  "symbols":["AAA"],"content_quality":"Q2","propositions":[]
}]}
seen=build(empty,store("genuine_forward","high"),prior=feature_prior,now="2026-10-07T00:00:00Z")
later=build(memory("price_above_ma50"),store("genuine_forward","high"),prior=seen,now="2026-10-08T00:00:00Z")
lc=later["candidates"][0]
assert lc["forward_observation_eligible"] is False
assert lc["formation_mode"]=="historical_or_retroactive"

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

# Supertrend without explicit ATR period/multiplier must fail closed.
r=build(memory("supertrend_bullish",True),store("genuine_forward","high"))
c=r["candidates"][0]
assert c["reproducibility_status"]=="blocked_needs_definition"
assert c["forward_observation_eligible"] is False
assert "period/multiplier" in c["unresolved_inputs"][0]["reason"]

print("PASS parameterized-indicator fail-closed semantics")

# Candidate identity must be family-level and role-aware for later dedup/comparison.
r=build(memory("price_above_ma50"),store("backfill"))
c=r["candidates"][0]
assert c["family_signature"].startswith("family_")
assert c["state_role"]=="trigger"
assert c["logic"]["trigger_conditions"]==["price_above_ma50"]
assert c["scope"]["subject_attribution"]=="single_symbol_source_scope"
print("PASS candidate family identity / lifecycle role")


# A source-supported prior-state -> invalidation sequence without an exact
# lookback window must remain partial, not be replayed as an impossible AND.
temporal=memory("price_above_ma50")
rule=temporal["records"][0]["propositions"][0]["evidence"]["candidate_rule"]
rule["state_hint"]="RISK"
rule["conditions"]=[
 {"condition_id":"price_above_ma50","semantic_role":"prior_observation"},
 {"condition_id":"price_below_ma50","semantic_role":"invalidation"},
 {"condition_id":"ma50_hold_two_sessions","semantic_role":"confirmation"},
]
tr=build(temporal,store("backfill"),prior={"source_observations":[]})
tc=tr["candidates"][0]
assert tc["reproducibility_status"]=="partial_needs_definition"
assert tc["historical_replay_eligible"] is False
assert tc["forward_observation_eligible"] is False
assert tc["logic"]["prior_observation_conditions"]==["price_above_ma50"]
assert tc["logic"]["invalidation_conditions"]==["price_below_ma50"]
assert tc["logic"]["confirmation_conditions"]==["ma50_hold_two_sessions"]
assert any(x["condition_id"]=="temporal_sequence_window" for x in tc["unresolved_inputs"])
print("PASS temporal sequence fail-closed semantics")


# Generic moving-average conditions are source-defined and machine reproducible.
for cid,indicator in [
 ("price_above_ma20","price_vs_ma20"),
 ("ma20_hold_two_sessions","price_vs_ma20"),
 ("price_above_ma200","price_vs_ma200"),
 ("ma200_hold_two_sessions","price_vs_ma200"),
]:
    rr=build(memory(cid),store("backfill"))
    x=rr["candidates"][0]
    assert x["reproducibility_status"]=="machine_ready_shadow", (cid,x)
    assert x["conditions"][0]["expression"]["indicator"]==indicator
    assert x["historical_replay_eligible"] is True
    assert x["production_eligible"] is False
print("PASS generic MA20/MA200 compiler coverage")


# Capability manifest keeps generic MA support machine-readable.
cap=build(memory("price_above_ma50"),store("backfill"))["capabilities"]
assert cap["generic_moving_average_support_complete"] is True
assert cap["generic_moving_average_windows"]==[20,50,200]
for cid in ("price_above_ma20","price_above_ma50","price_above_ma200"):
    assert cid in cap["machine_conditions"]
for cid in ("tcds_cross_zero","ppo_above_signal","supertrend_bullish"):
    assert cid in cap["parameterized_indicators_fail_closed"]
print("PASS generic candidate capability manifest")


# Explicit source-authored parameter definitions may unlock parameterized
# conditions; absent definitions remain blocked.
m=memory("macd_hist_positive")
cond=m["records"][0]["propositions"][0]["evidence"]["candidate_rule"]["conditions"][0]
cond["explicit_definition"]={
 "definition_source":"explicit_source_text","formula_id":"ema_macd",
 "fast_period":12,"slow_period":26,"signal_period":9,"smoothing":"EMA"
}
r=build(m,store("backfill"))
x=r["candidates"][0]
assert x["reproducibility_status"]=="machine_ready_shadow"
assert x["conditions"][0]["expression"]["formula_id"]=="ema_macd"
assert x["unresolved_inputs"]==[]
assert x["production_eligible"] is False

m2=memory("supertrend_bullish")
cond2=m2["records"][0]["propositions"][0]["evidence"]["candidate_rule"]["conditions"][0]
cond2["explicit_definition"]={
 "definition_source":"explicit_source_text","formula_id":"supertrend_atr_band",
 "atr_period":10,"multiplier":3.0,"atr_smoothing":"Wilder_RMA"
}
r2=build(m2,store("backfill"))
x2=r2["candidates"][0]
assert x2["reproducibility_status"]=="blocked_needs_definition"
assert x2["conditions"][0]["expression"] is None
assert x2["historical_replay_eligible"] is False
print("PASS explicit MACD unlock / incomplete Supertrend remains closed")
