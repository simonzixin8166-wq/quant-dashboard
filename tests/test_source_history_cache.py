import importlib.util
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("shc",ROOT/"scripts"/"source_history_cache.py")
shc=importlib.util.module_from_spec(spec);spec.loader.exec_module(shc)

source={"operation_cases":[
 {"published_at":"2026-08-18","symbols":["NBIS"],"operations":[
   {"symbols":["NBIS"],"entry_1":180,"attribution":"author_plan"},
   {"symbols":["META"],"actions":["buy"],"attribution":"third_party_example"}
 ]},
 {"published_at":"2026-05-01","symbols":["NBIS"],"operations":[
   {"symbols":["NBIS"],"actions":["buy"],"attribution":"author_action"}
 ]}
]}
req=shc.required_symbols(source)
assert req["NBIS"]=="2026-05-01"
assert "META" not in req

idx=pd.date_range("2026-01-01",periods=3)
raw=pd.DataFrame({"Open":[1,2,3],"High":[2,3,4],"Low":[.5,1.5,2.5],"Close":[1.5,2.5,3.5],"Volume":[10,20,30]},index=idx)
norm=shc.normalize_yf(raw,"NBIS")
assert list(norm.columns)==["open","high","low","close","volume"]
assert len(norm)==3
print("PASS source history cache")
