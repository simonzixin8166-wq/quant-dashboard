import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("at",ROOT/"scripts"/"v615_auto_thesis_engine.py")
at=importlib.util.module_from_spec(spec);spec.loader.exec_module(at)

off={
 "filings":[
   {"form":"10-Q","filing_date":"2026-10-01","accession":"x1","url":"https://sec.example/x","excerpts":["Results of Operations"]},
 ]
}
event={
 "news":[
   {"title":"IREN expands capacity","publisher":"Reuters","published_at":"2026-10-02T00:00:00Z","url":"https://example/n","uuid":"n1","source_type":"newswire"},
 ],
 "peer_context":{"direction":"broad_positive","peer_count":3}
}
row=at.build_symbol("IREN",off,event)
assert row["sources"]["official"][0]["evidence_class"]=="direct_company"
assert row["sources"]["events"][0]["evidence_class"]=="media"
assert row["sources"]["peer_context"]["evidence_class"]=="peer"
assert "Only direct_company evidence" in row["evidence_policy"]
assert row["guardrail"]

src=(ROOT/"scripts"/"official_evidence_engine.py").read_text(encoding="utf-8")
evt=(ROOT/"scripts"/"event_evidence_engine.py").read_text(encoding="utf-8")
assert 'PINNED_PUBLIC_RESEARCH=("IREN","SOFI")' in src
assert 'PINNED_PUBLIC_RESEARCH=("IREN","SOFI")' in evt
print("PASS V6.15 Auto Thesis evidence authority")
