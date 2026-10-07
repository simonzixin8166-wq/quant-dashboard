import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import pandas as pd
from scripts.candidate_forward_observer import build, verify_chain

def frame(vals,start="2026-01-01"):
    idx=pd.date_range(start,periods=len(vals),freq="B")
    return pd.DataFrame({"open":vals,"high":[x*1.01 for x in vals],"low":[x*.99 for x in vals],"close":vals,"volume":[1]*len(vals)},index=idx)

vals=[100.0]*55+[99.0]*3+[101.0,102.0]+[103.0]*70
df=frame(vals)
formed=(df.index[58]-pd.Timedelta(days=1)).date().isoformat()+"T00:00:00+00:00"
cand={
 "candidate_id":"c1","source_id":"s1","proposition_id":"p1","family_signature":"f1",
 "formation_mode":"forward_initial","forward_observation_eligible":True,
 "reproducibility_status":"machine_ready_shadow","unresolved_inputs":[],
 "scope":{"symbols":["AAA"]},"state_role":"trigger",
 "conditions":[{"condition_id":"ma50_hold_two_sessions","semantic_role":"confirmation","machine_ready":True}]
}
registry={"candidates":[cand],"source_observations":[{"source_id":"s1","first_candidate_compiler_seen_at":formed}]}

# Trim to the exact first state-entry day: no backfill, latest bar only.
short=df.iloc[:60]
store={"AAA":short,"QQQ":frame([100+i*.1 for i in range(len(short))])}
rows,status=build(registry,store,[],now="2026-04-01T00:00:00+00:00")
assert status["counts"]["eligible_candidates"]==1
assert status["counts"]["state_entries"]==1
assert rows[0]["record_type"]=="state_entry"
assert rows[0]["evidence_class"]=="genuine_forward_state_entry"
assert rows[0]["production_eligible"] is False
assert verify_chain(rows)

# Re-running the same completed bar is idempotent.
rows2,status2=build(registry,store,rows,now="2026-04-02T00:00:00+00:00")
assert status2["counts"]["state_entries"]==1
assert len(rows2)==1

# Later bars append outcomes without changing the state-entry.
full={"AAA":df,"QQQ":frame([100+i*.1 for i in range(len(df))])}
rows3,status3=build(registry,full,rows2,now="2026-08-01T00:00:00+00:00")
assert status3["counts"]["outcomes_5"]==1
assert status3["counts"]["outcomes_20"]==1
assert status3["counts"]["outcomes_60"]==1
assert len([x for x in rows3 if x["record_type"]=="state_entry"])==1
assert verify_chain(rows3)

# Backfill/non-forward candidates never enter the ledger.
bad=dict(cand);bad["candidate_id"]="c2";bad["forward_observation_eligible"]=False
rows4,status4=build({"candidates":[bad],"source_observations":[]},full,[],now="2026-08-01T00:00:00+00:00")
assert rows4==[]
assert status4["counts"]["eligible_candidates"]==0

# Tampering with an append-only row causes fail-closed status.
tampered=[dict(rows3[0])];tampered[0]["baseline_close"]=999
_,bad_status=build(registry,full,tampered,now="2026-08-02T00:00:00+00:00")
assert bad_status["status"]=="fail_closed_hash_chain_invalid"
assert bad_status["production_effect"]=="none"

print("PASS candidate forward observer append-only / state-entry / maturity / hash-chain")
