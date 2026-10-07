import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import pandas as pd
from scripts.candidate_rule_replay import build, resolve_store

def frame(vals):
    idx=pd.date_range("2026-01-01",periods=len(vals),freq="B")
    return pd.DataFrame({"open":vals,"high":[x*1.01 for x in vals],"low":[x*.99 for x in vals],"close":vals,"volume":[1]*len(vals)},index=idx)

vals=[100.0]*55+[99.0]*3+[101.0,102.0,103.0,104.0,105.0]+[106.0]*265
cand={
 "candidate_id":"cand1","reproducibility_status":"machine_ready_shadow",
 "scope":{"symbols":["AAA"]},"state_role":"trigger","method_family":"trend_confirmation",
 "conditions":[{"condition_id":"price_above_ma50","machine_ready":True}]
}
qqq=frame([100+i*.1 for i in range(len(vals))])
out=build({"candidates":[cand]},{"AAA":frame(vals),"QQQ":qqq})
row=out["candidates"][0]
assert row["status"]=="replayed"
assert row["raw_events"]>=1
assert row["statistics"]["5"]["raw_n"]>=1
assert "regime_split" in row
assert row["walk_forward"]["mode"]=="fixed_rule_chronological_no_fitting"
assert row["no_lookahead"]["future_bars_used_only_for_outcomes"] is True
assert out["validation_contract"]["baseline"].startswith("QQQ")
assert out["forward_evidence_mixed"] is False
assert out["automatic_promotion"] is False
assert out["production_effect"]=="none"

bad=dict(cand);bad["candidate_id"]="cand2";bad["reproducibility_status"]="blocked_needs_definition"
out=build({"candidates":[bad]},{"AAA":frame(vals)})
assert out["candidates"][0]["status"]=="blocked"

multi=dict(cand);multi["candidate_id"]="cand3";multi["scope"]={"symbols":["AAA","BBB"]}
out=build({"candidates":[multi]},{"AAA":frame(vals),"BBB":frame(vals)})
assert out["candidates"][0]["reason"]=="single_symbol_scope_required"

# Missing candidate symbols are resolved on demand for research replay only.
calls=[]
def fake_fetch(symbol):
    calls.append(symbol)
    return frame(vals)
store,prov=resolve_store({"candidates":[cand]}, {"QQQ":qqq}, fetcher=fake_fetch)
assert "AAA" in store and calls==["AAA"]
assert prov["AAA"]["source"]=="test_or_custom_research_provider"
assert prov["AAA"]["status"]=="ready"

# Fetch failure remains explicit and fail-closed.
def fail_fetch(symbol):
    raise RuntimeError("network unavailable")
store,prov=resolve_store({"candidates":[cand]}, {"QQQ":qqq}, fetcher=fail_fetch)
out=build({"candidates":[cand]},store,prov)
assert out["candidates"][0]["status"]=="blocked"
assert prov["AAA"]["status"]=="blocked"

print("PASS candidate rule historical replay / walk-forward / regime / no-lookahead")


# Identical state-entry histories across different Candidate instances are
# reported as overlap, not as independent system-level evidence.
cand_b=dict(cand)
cand_b["candidate_id"]="cand_overlap"
cand_b["state_role"]="confirmation"
dup=build({"candidates":[cand,cand_b]},{"AAA":frame(vals),"QQQ":qqq})
assert dup["summary"]["raw_events"]==2*dup["summary"]["cross_candidate_unique_state_entries"]
assert dup["summary"]["cross_candidate_duplicate_event_instances"]==dup["summary"]["cross_candidate_unique_state_entries"]
assert dup["summary"]["cross_candidate_overlap_rate"]==0.5
assert all(x["cross_candidate_overlap_events"]==x["raw_events"] for x in dup["candidates"])
print("PASS cross-candidate historical overlap accounting")


# MA20 / MA200 source-defined conditions replay without hidden parameters.
for cid in ("price_above_ma20","ma20_hold_two_sessions","price_above_ma200","ma200_hold_two_sessions"):
    x=dict(cand)
    x["candidate_id"]="cand_"+cid
    x["conditions"]=[{"condition_id":cid,"machine_ready":True}]
    replayed=build({"candidates":[x]},{"AAA":frame([100.0]*210+[101.0,102.0,103.0]+[104.0]*120),"QQQ":frame([100+i*.01 for i in range(333)])})
    row=replayed["candidates"][0]
    assert row["status"]=="replayed", (cid,row)
    assert row["raw_events"]>=1, (cid,row["raw_events"])
print("PASS generic MA20/MA200 historical replay")


# Explicit source-defined MACD/PPO/Supertrend formulas replay without defaults.
long_vals=[100+i*0.05 for i in range(420)]
hist=frame(long_vals)
param_cases=[
 ("macd_hist_positive",{"formula_id":"ema_macd","fast_period":12,"slow_period":26,"signal_period":9,"smoothing":"EMA"}),
 ("ppo_above_signal",{"formula_id":"ema_ppo","fast_period":12,"slow_period":26,"signal_period":9,"smoothing":"EMA"}),
 ("ppo_hist_positive",{"formula_id":"ema_ppo","fast_period":12,"slow_period":26,"signal_period":9,"smoothing":"EMA"}),
 ("supertrend_bullish",{"formula_id":"supertrend_atr_band","atr_period":10,"multiplier":3.0,"atr_smoothing":"Wilder_RMA"}),
]
for cid,expr in param_cases:
    x=dict(cand)
    x["candidate_id"]="param_"+cid
    x["conditions"]=[{"condition_id":cid,"machine_ready":True,"expression":expr}]
    res=build({"candidates":[x]},{"AAA":hist,"QQQ":frame([100+i*.03 for i in range(420)])})
    row=res["candidates"][0]
    assert row["status"]=="replayed", (cid,row)
    assert row["raw_events"]>=1, (cid,row["raw_events"])
print("PASS source-explicit parameterized indicator replay")
