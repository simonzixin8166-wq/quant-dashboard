from pathlib import Path
import importlib.util
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("foc",ROOT/"scripts"/"fundamental_outcome_context.py")
foc=importlib.util.module_from_spec(spec);spec.loader.exec_module(foc)

idx=pd.bdate_range("2026-09-01",periods=70)
df=pd.DataFrame({"open":[100+i for i in range(70)],"close":[101+i for i in range(70)],"low":[99+i for i in range(70)],"high":[102+i for i in range(70)]},index=idx)
auto={"symbols":{"TEST":{"sources":{"official":[{"date":"2026-09-02","form":"8-K","evidence_class":"direct_company"},{"date":"2026-09-02","form":"8-K","evidence_class":"direct_company"},{"date":"2026-09-03","form":"8-K","evidence_class":"peer"}]}}}}
out=foc.build(auto,{"TEST":df})
assert out["summary"]["linked_direct_events"]==1
assert out["summary"]["mature_5"]==1
assert out["summary"]["mature_20"]==1
assert out["summary"]["mature_60"]==1
row=out["rows"][0]
assert row["symbol"]=="TEST"
assert row["outcomes"]["5"]["return"] is not None
assert "thesis-correctness" in out["guardrail"]
print("PASS fundamental descriptive outcome context")

# #133 6458368830 §E: a stale upstream is reported, never a silent 0 (10/28: SEC filings were back in
# official_evidence.json while auto_thesis_drafts.json had been built from the previous evidence file).
official = {"generated_at": "2026-10-28T01:21:28Z", "symbols": {"TEST": {"status": "ok", "filings": [{"form": "8-K"}]},
                                                                 "ETF": {"status": "unmapped", "filings": []}}}
assert out["upstream"]["status"] == "ok"                                     # no official file given -> nothing to compare
stale = foc.build({"generated_at": "2026-10-28T01:21:20Z", "symbols": {"TEST": {"sources": {"official": []}}}},
                  {"TEST": df}, official)
up = stale["upstream"]
assert up["status"] == "stale_upstream" and up["official_symbols_with_filings"] == 1 and up["auto_thesis_direct_symbols"] == 0
assert up["auto_thesis_older_than_official"] is True and stale["summary"]["linked_direct_events"] == 0
fresh = foc.build(dict(auto, generated_at="2026-10-28T01:25:00Z"), {"TEST": df}, official)
assert fresh["upstream"]["status"] == "ok" and fresh["upstream"]["auto_thesis_direct_symbols"] == 1
quiet = foc.build({"symbols": {}}, {}, {"symbols": {"X": {"filings": []}}})   # SEC down, nothing filed: not stale
assert quiet["upstream"]["status"] == "ok"

# the workflow builds Auto Thesis after both evidence layers and before every consumer (no read-before-write)
wf = (ROOT / ".github" / "workflows" / "source-intelligence-validation.yml").read_text(encoding="utf-8").splitlines()
pos = {name: next(i for i, l in enumerate(wf) if f"run: python scripts/{name}.py" in l)
       for name in ("official_evidence_engine", "event_evidence_engine", "v615_auto_thesis_engine",
                    "fundamental_outcome_context", "learning_evaluation_engine", "data_learning_coverage_audit")}
assert pos["official_evidence_engine"] < pos["v615_auto_thesis_engine"] and pos["event_evidence_engine"] < pos["v615_auto_thesis_engine"]
assert pos["v615_auto_thesis_engine"] < min(pos["fundamental_outcome_context"], pos["learning_evaluation_engine"],
                                            pos["data_learning_coverage_audit"])
print("PASS upstream freshness (stale_upstream instead of a silent 0) and Auto Thesis step order")
