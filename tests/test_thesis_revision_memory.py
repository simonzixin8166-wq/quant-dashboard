from pathlib import Path
import tempfile,sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import v615_auto_thesis_engine as m

with tempfile.TemporaryDirectory() as td:
    old=m.THESIS_ARCHIVE;m.THESIS_ARCHIVE=Path(td)
    try:
        out={"generated_at":"2026-10-08T00:00:00Z","symbols":{"ABC":{
          "evidence_hash":"h1","evidence_summary":"10-Q 2026","catalysts":"c","risks":"r",
          "invalidation":"i","valuation_note":"","sources":{"official":[{"url":"https://sec/a"}],"events":[]}
        }}}
        assert m.append_thesis_revisions(out)==1
        assert m.append_thesis_revisions(out)==0
        out["generated_at"]="2026-10-09T00:00:00Z";out["symbols"]["ABC"]["evidence_hash"]="h2"
        assert m.append_thesis_revisions(out)==1
        rows=[json.loads(x) for x in (Path(td)/"ABC.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows)==2
        assert rows[-1]["previous_evidence_hash"]=="h1"
        assert rows[-1]["change_reason"]=="evidence_hash_changed"
        assert rows[-1]["production_effect"]=="none"
    finally:m.THESIS_ARCHIVE=old
print("PASS append-only thesis revision memory")
