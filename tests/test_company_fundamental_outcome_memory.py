from pathlib import Path
import tempfile,sys,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import company_fundamental_outcome_memory as m

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    old_arch,old_obs,old_out,old_summary=m.ARCH,m.OBS,m.OUTCOMES,m.OUT
    m.ARCH=root/"fund";m.OBS=root/"obs.jsonl";m.OUTCOMES=root/"out.jsonl";m.OUT=root/"summary.json"
    m.ARCH.mkdir(parents=True)
    rows=[
      {"observation_id":"r1","symbol":"ABC","metric":"revenue","concept":"Revenue","unit":"USD","value":100,
       "start":"2025-01-01","end":"2025-03-31","filed":"2025-05-01","form":"10-Q","accn":"a1"},
      {"observation_id":"r2","symbol":"ABC","metric":"revenue","concept":"Revenue","unit":"USD","value":120,
       "start":"2026-01-01","end":"2026-03-31","filed":"2026-05-01","form":"10-Q","accn":"a2"},
      {"observation_id":"n2","symbol":"ABC","metric":"net_income","concept":"NetIncome","unit":"USD","value":12,
       "start":"2026-01-01","end":"2026-03-31","filed":"2026-05-01","form":"10-Q","accn":"a2"}
    ]
    (m.ARCH/"ABC.jsonl").write_text("\n".join(json.dumps(x) for x in rows)+"\n",encoding="utf-8")
    idx=pd.bdate_range("2025-05-02",periods=400)
    df=pd.DataFrame({"open":range(100,500),"high":range(101,501),"low":range(99,499),"close":range(100,500)},index=idx)
    try:
        obs=m.build_observations()
        current=[x for x in obs if x["accn"]=="a2"][0]
        assert round(current["metrics"]["revenue"]["yoy_pct"],1)==20.0
        assert round(current["derived"]["net_margin_pct"],1)==10.0
        out=m.run({"ABC":df})
        assert out["counts"]["observations"]==2
        assert out["counts"]["outcomes"]>=2
        assert out["horizons"]["20"]["n"]>=1
        again=m.run({"ABC":df})
        assert again["counts"]["observations_added"]==0
        assert again["counts"]["outcomes_added"]==0
    finally:
        m.ARCH,m.OBS,m.OUTCOMES,m.OUT=old_arch,old_obs,old_out,old_summary

print("PASS XBRL point-in-time fundamental outcome memory")
