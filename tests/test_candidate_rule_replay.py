import pandas as pd
from scripts.candidate_rule_replay import build

def frame(vals):
    idx=pd.date_range("2026-01-01",periods=len(vals),freq="B")
    return pd.DataFrame({"open":vals,"high":[x*1.01 for x in vals],"low":[x*.99 for x in vals],"close":vals,"volume":[1]*len(vals)},index=idx)

# Price below MA50 then crosses above once; replay counts state entry, not every day.
vals=[100.0]*55+[99.0]*3+[101.0,102.0,103.0,104.0,105.0]+[106.0]*65
cand={
 "candidate_id":"cand1","reproducibility_status":"machine_ready_shadow",
 "scope":{"symbols":["AAA"]},"state_role":"trigger","method_family":"trend_confirmation",
 "conditions":[{"condition_id":"price_above_ma50","machine_ready":True}]
}
out=build({"candidates":[cand]},{"AAA":frame(vals),"QQQ":frame([100+i*.1 for i in range(len(vals))])})
row=out["candidates"][0]
assert row["status"]=="replayed"
assert row["raw_events"]>=1
assert out["forward_evidence_mixed"] is False
assert out["automatic_promotion"] is False
assert out["production_effect"]=="none"

# Unresolved/partial candidates are never replayed.
bad=dict(cand)
bad["candidate_id"]="cand2";bad["reproducibility_status"]="blocked_needs_definition"
out=build({"candidates":[bad]},{"AAA":frame(vals)})
assert out["candidates"][0]["status"]=="blocked"

# Multi-symbol scope is fail-closed.
multi=dict(cand)
multi["candidate_id"]="cand3";multi["scope"]={"symbols":["AAA","BBB"]}
out=build({"candidates":[multi]},{"AAA":frame(vals),"BBB":frame(vals)})
assert out["candidates"][0]["reason"]=="single_symbol_scope_required"

print("PASS candidate rule historical replay")
