import importlib.util
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("mm",ROOT/"scripts"/"method_memory_engine.py")
mm=importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)

source={
 "counts":{"records":3},
 "records":[
  {"url":"u1","author":"A","topics":["趋势确认"],"title":"QQQ breakout"},
  {"url":"u2","author":"A","topics":["风险管理","趋势确认"],"title":"risk + trend"},
  {"url":"u3","author":"B","topics":["其他研究"],"title":"noise"},
 ]
}
validation={"events":[
 {"event_id":"e1","url":"u1","author":"A","symbol":"QQQ","attribution":"author_action","triggered":True,
  "baseline_date":"2026-01-06","outcomes":{"5":{"return":0.05,"mae":-0.02,"mfe":0.08,"excess_vs_qqq":0.0},"20":{"return":0.08,"mae":-0.03,"mfe":0.12,"excess_vs_qqq":0.0},"60":None},
  "alignment":{"5":"aligned","20":"aligned","60":None},"title":"QQQ breakout"},
 {"event_id":"e2","url":"u2","author":"A","symbol":"NVDA","attribution":"author_plan","triggered":True,
  "baseline_date":"2026-01-07","outcomes":{"5":{"return":-0.03,"mae":-0.08,"mfe":0.02,"excess_vs_qqq":-0.04},"20":None,"60":None},
  "alignment":{"5":"not_aligned","20":None,"60":None},"title":"risk + trend"},
 {"event_id":"e3","url":"u1","author":"A","symbol":"QQQ","attribution":"unconfirmed_author_context","triggered":True,
  "baseline_date":"2026-01-08","outcomes":{"5":{"return":1.0,"mae":0,"mfe":1.0},"20":None,"60":None},
  "alignment":{"5":"aligned","20":None,"60":None},"title":"excluded"},
]}

idx=pd.date_range("2025-10-01",periods=100,freq="B")
qqq=pd.DataFrame({"open":range(100,200),"high":range(101,201),"low":range(99,199),"close":range(100,200),"volume":[1]*100},index=idx)
out=mm.build(source,validation,{"QQQ":qqq},{})
trend=next(x for x in out["methods"] if x["method"]=="趋势确认")
risk=next(x for x in out["methods"] if x["method"]=="风险管理")
assert out["counts"]["validated_triggered_events"]==2
assert trend["source_occurrences"]==2
assert trend["validated_triggered_events"]==2
assert trend["performance"]["5"]["n"]==2
assert trend["performance"]["5"]["avg_mae"] is not None
assert risk["validated_triggered_events"]==1
assert risk["failure_examples"][0]["event_id"]=="e2"
assert "trend_positive" in trend["market_context_counts"]
print("PASS method memory engine")
