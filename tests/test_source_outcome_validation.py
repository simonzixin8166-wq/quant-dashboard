import importlib.util
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("sov",ROOT/"scripts"/"source_outcome_validation.py")
sov=importlib.util.module_from_spec(spec);spec.loader.exec_module(sov)

idx=pd.bdate_range("2026-08-18",periods=70)
def frame(start,step):
    close=[start+i*step for i in range(len(idx))]
    return pd.DataFrame({"open":close,"high":[x*1.01 for x in close],"low":[x*0.99 for x in close],"close":close,"volume":[1]*len(idx)},index=idx)
store={"NBIS":frame(170,2),"QQQ":frame(700,1)}
src={"operation_cases":[
 {"id":"a","author":"BrightLine","published_at":"2026-08-18","title":"子弹与耐心","url":"https://example.com/a","symbols":["NBIS"],"operations":[
   {"symbols":["NBIS"],"entry_1":180,"entry_2":150,"exit_line":250,"actions":["buy"],"attribution":"author_plan","attribution_confidence":"high"}
 ]},
 {"id":"b","author":"BrightLine","published_at":"2026-08-18","title":"段永平案例","url":"https://example.com/b","symbols":["NBIS"],"operations":[
   {"symbols":["NBIS"],"actions":["buy"],"attribution":"third_party_example","attribution_confidence":"high"}
 ]}
]}
out=sov.build(src,store)
assert out["counts"]["events"]==1
assert out["counts"]["author_owned"]==1
e=out["events"][0]
assert e["attribution"]=="author_plan"
assert e["outcomes"]["5"] is not None
assert e["level_checks"]["entry_1"]["touch20"]["touched"] is True
assert e["level_checks"]["exit_line"]["touch60"]["touched"] is True
assert e["alignment"]["20"] in {"aligned","not_aligned"}
print("PASS source outcome validation")
