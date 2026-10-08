from pathlib import Path
import tempfile,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import market_state_outcome_scorecards as m

idx=pd.bdate_range("2026-01-02",periods=90)
spy=pd.DataFrame({
 "open":[100+i*.2 for i in range(90)],
 "high":[101+i*.2 for i in range(90)],
 "low":[99+i*.2 for i in range(90)],
 "close":[100+i*.2 for i in range(90)],
},index=idx)
row={"as_of":str(idx[5].date()),"anchor_spy":101.0,"level":"high","state_id":"RISK"}
with tempfile.TemporaryDirectory() as td:
    old_arch,old_out,old_cross,old_breadth,old_regime=m.ARCH,m.OUT,m.CROSS,m.BREADTH,m.REGIME
    m.ARCH=Path(td)/"outcomes.jsonl";m.OUT=Path(td)/"summary.json"
    m.CROSS=Path(td)/"cross.json";m.BREADTH=Path(td)/"breadth.json";m.REGIME=Path(td)/"regime.json"
    for p in [m.CROSS,m.BREADTH,m.REGIME]:
        p.write_text('{"records":['+__import__("json").dumps(row)+']}',encoding="utf-8")
    try:
        out=m.run({"SPY":spy})
        assert out["counts"]["outcomes"]==9
        assert out["counts"]["scorecards"]==9
        again=m.run({"SPY":spy})
        assert again["counts"]["added"]==0
    finally:
        m.ARCH,m.OUT,m.CROSS,m.BREADTH,m.REGIME=old_arch,old_out,old_cross,old_breadth,old_regime
print("PASS market-state 5/20/60 outcome scorecards")
