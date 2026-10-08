from pathlib import Path
import tempfile,sys,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import event_outcome_memory as m

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    old_dir,old_out,old_summary=m.EVENT_DIR,m.OUTCOMES,m.OUT
    m.EVENT_DIR=root/"events";m.OUTCOMES=root/"outcomes.jsonl";m.OUT=root/"summary.json"
    m.EVENT_DIR.mkdir(parents=True)
    event={"archive_id":"e1","symbol":"ABC","published_at":"2026-01-05T12:00:00Z","title":"event","publisher":"Reuters","source_type":"newswire","source_priority":1}
    (m.EVENT_DIR/"2026-01.jsonl").write_text(json.dumps(event)+"\n",encoding="utf-8")
    idx=pd.bdate_range("2026-01-02",periods=90)
    abc=pd.DataFrame({"open":[100+i*.5 for i in range(90)],"high":[101+i*.5 for i in range(90)],"low":[99+i*.5 for i in range(90)],"close":[100+i*.5 for i in range(90)]},index=idx)
    spy=pd.DataFrame({"open":[100+i*.1 for i in range(90)],"high":[101+i*.1 for i in range(90)],"low":[99+i*.1 for i in range(90)],"close":[100+i*.1 for i in range(90)]},index=idx)
    try:
        out=m.run({"ABC":abc,"SPY":spy})
        assert out["counts"]["events"]==1
        assert out["counts"]["outcomes"]==3
        assert out["horizons"]["20"]["n"]==1
        assert out["benchmark"]=="SPY"
        rows=m.read_jsonl(m.OUTCOMES)
        assert all(x["causal_claim"] is False for x in rows)
        assert all(x["excess_return_pct"] is not None for x in rows)
        again=m.run({"ABC":abc,"SPY":spy})
        assert again["counts"]["outcomes_added"]==0
    finally:
        m.EVENT_DIR,m.OUTCOMES,m.OUT=old_dir,old_out,old_summary
print("PASS benchmark-adjusted event outcome memory")
