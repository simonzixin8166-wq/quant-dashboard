from pathlib import Path
import tempfile,sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import operational_incident_memory as m

bad={"generated_at":"2026-10-08T00:00:00Z","workflows":{"quant-dashboard":{"Daily":{"health":"bad","status":"completed","conclusion":"failure","head_sha":"a","updated_at":"x"}}},"artifacts":{"market":{"freshness":"fresh","business_freshness":"stale","market_as_of":"2026-10-06","expected_market_date":"2026-10-07"}}}
good={"generated_at":"2026-10-08T01:00:00Z","workflows":{"quant-dashboard":{"Daily":{"health":"ok","status":"completed","conclusion":"success"}}},"artifacts":{"market":{"freshness":"fresh","business_freshness":"fresh"}}}

with tempfile.TemporaryDirectory() as td:
    old_state,old_arch,old_out=m.STATE,m.ARCH,m.OUT
    m.STATE=Path(td)/"state.json";m.ARCH=Path(td)/"incidents.jsonl";m.OUT=Path(td)/"out.json"
    try:
        a=m.run(bad,"2026-10-08T00:00:01Z")
        assert a["counts"]["open"]==2
        assert a["counts"]["opened_this_run"]==2
        b=m.run(bad,"2026-10-08T00:30:00Z")
        assert b["counts"]["opened_this_run"]==0
        c=m.run(good,"2026-10-08T01:00:01Z")
        assert c["counts"]["open"]==0
        assert c["counts"]["resolved_this_run"]==2
        rows=[json.loads(x) for x in m.ARCH.read_text(encoding="utf-8").splitlines()]
        assert [x["event"] for x in rows].count("opened")==2
        assert [x["event"] for x in rows].count("resolved")==2
    finally:
        m.STATE,m.ARCH,m.OUT=old_state,old_arch,old_out
print("PASS operational incident opened/resolved memory")
