import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import pandas as pd
from scripts.candidate_event_score import adapt
from scripts.evaluation_spec import load_spec

def frame(n=400):
    idx=pd.date_range("2025-01-02",periods=n,freq="B")
    vals=[100+i*.1 for i in range(n)]
    return pd.DataFrame({"open":vals,"high":[x*1.01 for x in vals],"low":[x*.99 for x in vals],"close":[x*1.002 for x in vals],"volume":[1]*n},index=idx)

df=frame()
signal_date=df.index[250].date().isoformat()
baseline_date=df.index[251].date().isoformat()
entry={
 "record_type":"state_entry","event_id":"e1","candidate_id":"c1","family_signature":"f1",
 "candidate_snapshot_hash":"a"*64,"author":"tester","source_id":"s1","source_url":"u",
 "symbol":"AAA","signal_date":signal_date,"expected_direction":"bullish",
 "candidate_first_compiler_seen_at":str(df.index[249].date())+"T00:00:00+00:00",
 "source_first_fetched_at":str(df.index[249].date())+"T00:00:00+00:00",
 "source_admission_class":"genuine_forward"
}
baseline={
 "record_type":"baseline","event_id":"e1","candidate_id":"c1","family_signature":"f1",
 "symbol":"AAA","baseline_date":baseline_date,"baseline_open":float(df.iloc[251]["open"])
}
outcome={
 "record_type":"outcome","event_id":"e1","candidate_id":"c1","family_signature":"f1",
 "symbol":"AAA","baseline_date":baseline_date,"horizon":20,
 "maturity_date":df.index[271].date().isoformat(),
 "return":float(df.iloc[271]["close"]/df.iloc[251]["open"]-1),
 "mae":-0.01,"mfe":0.04,"benchmark_return":0.01,"excess_vs_qqq":0.02
}
histories={"AAA":{"df":df,"meta":{
 "status":"ok","price_source":"stooq_archive","source":"stooq_archive",
 "adjustment_basis":"stooq_archive_native_series","same_source_only":True
}}}
res=adapt([entry,baseline,outcome],histories,load_spec())
ev=res["events"][0]
assert res["spec_version"]=="1.7"
assert ev["entry_type"]=="next_session"
assert ev["scoreable"] is True
assert ev["maturity"]["20"] is True
assert ev["scores"]["20"]["unconditional_lift"] is not None
assert ev["scores"]["20"]["direction_adjusted_mae"] is not None
assert ev["promotion_gate_compatible"] is False
assert ev["promotion_gate_blocker"].startswith("frozen_rule_family_direction")
assert res["production_effect"]=="none"
assert res["promotion_effect"]=="none"

# Missing baseline fails closed.
res2=adapt([entry],histories,load_spec())
assert res2["events"][0]["scoreable"] is False
assert res2["events"][0]["primary_exclusion_reason"]=="missing_next_session_open_baseline"

# Non-genuine source provenance fails closed even with complete prices.
bad=dict(entry);bad["source_admission_class"]="backfill"
res3=adapt([bad,baseline,outcome],histories,load_spec())
assert res3["events"][0]["scoreable"] is False
assert res3["events"][0]["point_in_time_status"]=="source_not_genuine_forward"

print("PASS candidate EventScore Spec 1.7 metrics / fail-closed Promotion bridge")
