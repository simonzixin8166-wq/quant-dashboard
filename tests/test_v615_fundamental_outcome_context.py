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
