from pathlib import Path
import json,tempfile,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import thesis_revision_outcome_memory as m

idx=pd.bdate_range("2026-01-02",periods=90)
def frame(base,step):
    return pd.DataFrame({
      "open":[base+i*step for i in range(len(idx))],
      "high":[base+i*step+1 for i in range(len(idx))],
      "low":[base+i*step-1 for i in range(len(idx))],
      "close":[base+i*step for i in range(len(idx))],
    },index=idx)
stock=frame(100,1.0);bench=frame(100,0.5)
rev={"symbol":"ABC","revision_at":"2026-01-05T00:00:00+00:00","evidence_hash":"h1","previous_evidence_hash":None,"change_reason":"initial_thesis"}

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    old_rev,old_outcomes,old_out=m.REV_DIR,m.OUTCOMES,m.OUT
    m.REV_DIR=root/"revs";m.OUTCOMES=root/"outcomes.jsonl";m.OUT=root/"summary.json"
    m.REV_DIR.mkdir()
    (m.REV_DIR/"ABC.jsonl").write_text(json.dumps(rev)+"\n",encoding="utf-8")
    try:
        out=m.run({"ABC":stock,"QQQ":bench})
        assert out["counts"]["revisions"]==1
        assert out["counts"]["outcomes"]==3
        assert out["counts"]["outcomes_added"]==3
        assert out["horizons"]["5"]["n"]==1
        again=m.run({"ABC":stock,"QQQ":bench})
        assert again["counts"]["outcomes_added"]==0
        rows=[json.loads(x) for x in m.OUTCOMES.read_text(encoding="utf-8").splitlines()]
        assert all(x["causal_claim"] is False for x in rows)
        assert all(x["production_effect"]=="none" for x in rows)
    finally:
        m.REV_DIR,m.OUTCOMES,m.OUT=old_rev,old_outcomes,old_out
print("PASS thesis revision benchmark-adjusted outcome memory")
