from pathlib import Path
import tempfile,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import options_opportunity_outcome_memory as m

idx=pd.bdate_range("2026-01-02",periods=35)
df=pd.DataFrame({
 "open":[100+i for i in range(35)],
 "high":[101+i for i in range(35)],
 "low":[99+i for i in range(35)],
 "close":[100+i for i in range(35)],
},index=idx)
# price 101.0 is the 2026-01-05 close; the snapshot is dated by that session.
doc={"generated_at":"2026-01-06T03:00:00Z","records":{"ABC":{
 "price_as_of":"2026-01-05","support_as_of":"2026-01-05","inputs_aligned":True,"as_of":"2026-01-05",
 "state":"chain_scan_candidate","status":"scan_context_ready","scan_priority":"high",
 "scan_lanes":["SELL_PUT_CHAIN_SCAN"],"research_modes":["SELL_PUT_SCREEN"],
 "reasons":["strong_support_plus_volatility"],
 "required_before_strategy_candidate":["live_option_chain"],
 "context":{"price":101.0,"rsi14":40,"near_strong_support":True,"forecast_vol_expanding":True,"trend_constructive":False,"structurally_weak":False}
}}}

with tempfile.TemporaryDirectory() as td:
    old_obs,old_out,old_summary,old_sup=m.OBS,m.OUTCOMES,m.OUT,m.SUPERSESSIONS
    m.OBS=Path(td)/"obs";m.OUTCOMES=Path(td)/"out";m.OUT=Path(td)/"summary.json";m.SUPERSESSIONS=Path(td)/"sup.jsonl"
    try:
        out=m.run(doc,{"ABC":df})
        assert out["counts"]["observations"]==1
        assert out["counts"]["matured"]==2
        assert out["counts"]["outcomes_added"]==2
        again=m.run(doc,{"ABC":df})
        assert again["counts"]["observations_added"]==0
        assert again["counts"]["outcomes_added"]==0
        assert again["horizons"]["5"]["n"]==1
        assert again["horizons"]["20"]["n"]==1

        # Same session re-run with a different research state: still one frozen sample.
        import copy, json
        changed=copy.deepcopy(doc);changed["records"]["ABC"]["state"]="context_only";changed["generated_at"]="2026-01-06T09:00:00Z"
        third=m.run(changed,{"ABC":df})
        assert third["counts"]["observations_added"]==0 and third["counts"]["observations"]==1

        # Mixed-session inputs and a missing price date are never frozen (no generated-date fallback).
        mixed=copy.deepcopy(doc);mixed["records"]["ABC"].update({"price_as_of":"2026-01-06","support_as_of":"2026-01-07","inputs_aligned":False})
        r=m.run(mixed,{"ABC":df})
        assert r["counts"]["observations_added"]==0 and r["counts"]["skipped_this_run"]=={"inputs_not_aligned":1}
        nodate=copy.deepcopy(doc);[nodate["records"]["ABC"].pop(k) for k in ("price_as_of","as_of")]
        r=m.run(nodate,{"ABC":df})
        assert r["counts"]["observations_added"]==0 and r["counts"]["skipped_this_run"]=={"price_as_of_missing":1}

        # Legacy (schema 1) rows stay on disk, are superseded append-only, and never mature.
        legacy={"observation_id":"legacy1","symbol":"ABC","as_of":"2026-01-06","price":101.0,"state":"chain_scan_candidate"}
        with (m.OBS/"2026-01.jsonl").open("a",encoding="utf-8") as f:f.write(json.dumps(legacy)+"\n")
        r=m.run(doc,{"ABC":df})
        assert r["counts"]["superseded_legacy"]==1 and r["counts"]["observations"]==1
        assert r["horizons"]["5"]["n"]==1
        assert "legacy1" in (m.OBS/"2026-01.jsonl").read_text(encoding="utf-8")
        sup=[json.loads(x) for x in m.SUPERSESSIONS.read_text(encoding="utf-8").splitlines()]
        assert [s["observation_id"] for s in sup]==["legacy1"]
        m.run(doc,{"ABC":df})
        assert len(m.SUPERSESSIONS.read_text(encoding="utf-8").splitlines())==1
    finally:
        m.OBS,m.OUTCOMES,m.OUT,m.SUPERSESSIONS=old_obs,old_out,old_summary,old_sup
# The supersession audit trail must be committed by both writers of this archive.
wf=(ROOT/".github"/"workflows"/"source-intelligence-validation.yml").read_text(encoding="utf-8")
assert "git add research/archive/options_opportunity_supersessions.jsonl" in wf
assert "git add docs/ research/archive/" in (ROOT/".github"/"workflows"/"daily.yml").read_text(encoding="utf-8")
print("PASS options opportunity observation/outcome memory")
