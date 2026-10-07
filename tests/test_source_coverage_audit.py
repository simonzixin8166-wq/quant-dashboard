import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.source_coverage_audit import build

authors=["BrightLine","yifan99","三心三意","我是一只井底蛙","bogbog"]
records=[]
for i,a in enumerate(authors):
    records.append({
      "id":f"w{i}","source":"wenxuecity","author":a,"published_at":"2026-10-06",
      "symbols":["AMZN"],"primary_symbols":["AMZN"],
      "symbol_attribution":[{"symbol":"AMZN","role":"primary_subject"}],
      "content_quality":"Q2"
    })
records.append({
 "id":"yt","source":"youtube","author":"老李玩钱","published_at":"2026-10-05",
 "symbols":["QQQ","TSLA"],"primary_symbols":[],
 "symbol_attribution":[{"symbol":"QQQ","role":"contextual_mention"},{"symbol":"TSLA","role":"comparison_peer"}],
 "content_quality":"Q2"
})
src={"generated_at":"2026-10-07T04:00:00+00:00","counts":{"records":1315},"records":records}
out=build(src)
assert out["state"]=="operational"
assert out["alerts"]==[]
assert out["window"]["source_intelligence_total_records"]==1315
assert out["quality"]["published_timestamp_parseable_ratio"]==1.0
assert out["quality"]["multi_symbol_records"]==1
assert out["quality"]["ambiguous_multi_symbol_records"]==1
assert not out["expected_coverage"]["missing_or_stale_authors"]
assert not out["expected_coverage"]["missing_or_stale_channels"]
assert out["production_effect"]=="none"

# Quiet/missing source produces attention only, never Production effect.
bad={"generated_at":"2026-10-07T04:00:00+00:00","counts":{"records":1},"records":[records[0]]}
out2=build(bad)
assert out2["state"]=="attention"
assert "yifan99" in out2["expected_coverage"]["missing_or_stale_authors"]
assert "youtube" in out2["expected_coverage"]["missing_or_stale_channels"]
assert out2["production_effect"]=="none"
assert out2["promotion_effect"]=="none"

print("PASS continuous source coverage audit / observational fail-safe")
