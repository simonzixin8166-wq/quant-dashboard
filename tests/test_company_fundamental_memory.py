from pathlib import Path
import tempfile,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import company_fundamental_memory as m

official={"symbols":{"ABC":{"cik":123,"company_name":"ABC Inc"}}}
payload={
 "entityName":"ABC Inc",
 "facts":{"us-gaap":{
   "RevenueFromContractWithCustomerExcludingAssessedTax":{"units":{"USD":[
     {"start":"2026-01-01","end":"2026-03-31","val":100,"filed":"2026-05-01","form":"10-Q","accn":"a1","fy":2026,"fp":"Q1"},
     {"start":"2026-01-01","end":"2026-03-31","val":101,"filed":"2026-05-10","form":"10-Q","accn":"a1a","fy":2026,"fp":"Q1"}
   ]}},
   "NetIncomeLoss":{"units":{"USD":[
     {"start":"2026-01-01","end":"2026-03-31","val":10,"filed":"2026-05-01","form":"10-Q","accn":"a1","fy":2026,"fp":"Q1"}
   ]}}
 }}
}
def fake(url,ua): return payload

with tempfile.TemporaryDirectory() as td:
    old=m.ARCH;m.ARCH=Path(td)
    try:
        out=m.build(official,fake,"test-agent")
        assert out["counts"]["archive_added"]==3
        assert out["symbols"]["ABC"]["latest"]["revenue"]["value"]==101
        assert out["symbols"]["ABC"]["latest"]["revenue"]["filed"]=="2026-05-10"
        out2=m.build(official,fake,"test-agent")
        assert out2["counts"]["archive_added"]==0
        lines=(Path(td)/"ABC.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines)==3
    finally:m.ARCH=old

print("PASS SEC CompanyFacts append-only point-in-time fundamental memory")
