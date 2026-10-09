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

# P0-1: tagged-only news is excluded; readiness lists have/missing and is never verified.
assert at.news_relevance("MSFT","Microsoft Corp","AMD vs ASML: which chip stock to buy")=="tagged_only"
assert at.news_relevance("MSFT","Microsoft Corp","Microsoft expands Azure capacity")=="direct"
assert at.news_relevance("NOW","ServiceNow Inc","Stocks to watch now")=="tagged_only"
mix={"news":[{"title":"AMD vs ASML chip stock","uuid":"t1","published_at":"2026-10-03T00:00:00Z"},
             {"title":"Microsoft signs new AI deal","uuid":"d1","published_at":"2026-10-04T00:00:00Z"}]}
r2=at.build_symbol("MSFT",{"company_name":"Microsoft Corp","filings":[{"form":"10-K","filing_date":"2026-07-29","accession":"k"}]},mix)
rd=r2["readiness"]
assert rd["verified"] is False and rd["status"]=="draft_only"
assert rd["excluded_tagged_only_news"]==1 and len(r2["sources"]["events"])==1
assert any("失效条件" in m for m in rd["missing"])
assert rd["last_evidence_date"]=="2026-10-04"
none=at.build_symbol("AMD",{},{})["readiness"]
assert none["status"]=="no_coverage" and not none["have"]
assert at.news_relevance("META","Meta Platforms","The meta trade in AI")=="tagged_only"
assert at.news_relevance("META","Meta Platforms","Meta unveils glasses")=="direct"
assert at.news_relevance("MU","Micron Technology","MICRON beats")=="direct"
print("PASS P0-1 readiness / news relevance")
