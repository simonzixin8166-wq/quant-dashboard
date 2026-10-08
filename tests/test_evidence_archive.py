from pathlib import Path
import json,tempfile,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from evidence_archive import build

official={"generated_at":"2026-10-08T00:00:00Z","symbols":{"ABC":{"cik":1,"company_name":"ABC Inc","filings":[
 {"form":"10-Q","accession":"0001","filing_date":"2026-10-07","report_date":"2026-09-30","url":"https://sec/1","document_status":"ok","excerpts":["x"]}
]}}}
events={"generated_at":"2026-10-08T00:00:00Z","symbols":{"ABC":{"news":[
 {"uuid":"n1","published_at":"2026-10-07T12:00:00Z","title":"ABC news","publisher":"Reuters","source_type":"newswire","source_priority":1,"url":"https://n/1","related_tickers":["ABC"]}
]}}}

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    first=build(official,events,root,now="2026-10-08T01:00:00Z")
    assert first["sec"]["new"]==1 and first["events"]["new"]==1
    assert first["sec"]["total"]==1 and first["events"]["total"]==1
    second=build(official,events,root,now="2026-10-08T02:00:00Z")
    assert second["sec"]["new"]==0 and second["events"]["new"]==0
    assert second["sec"]["total"]==1 and second["events"]["total"]==1
    sec=(root/"sec_filings"/"2026-10.jsonl").read_text(encoding="utf-8").splitlines()
    ev=(root/"events"/"2026-10.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(sec)==1 and len(ev)==1
    assert json.loads(sec[0])["source"]=="SEC EDGAR official"
    assert json.loads(ev[0])["source_priority"]==1

print("PASS append-only SEC/Event evidence archive")
