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

# SRC-02 (#133 6391860281): with the canonical store, undated records are counted instead of vanishing past the
# 800-row window; a channel that only receives undated records is "active_undated" (P2), not missing (P1).
def srow(rec, published, fetched, online=True):
    return {"record": rec, "published_at": published, "first_fetched_at": fetched, "source_still_online": online}
store = {"records": [srow(r, r["published_at"], "2026-10-06T00:00:00Z") for r in records[:5]] + [
    srow({"id": "y1", "source": "youtube", "author": "老李玩钱"}, "", "2026-10-06T05:00:00Z"),
    srow({"id": "y2", "source": "youtube", "author": "老李玩钱"}, "", "2026-08-01T05:00:00Z")]}
window_only = {"generated_at": "2026-10-07T04:00:00+00:00", "counts": {"records": 7}, "records": records[:5]}
assert "youtube" in build(window_only)["expected_coverage"]["missing_or_stale_channels"]        # old blind spot
out3 = build(window_only, store)
yt = next(c for c in out3["expected_coverage"]["channels"] if c["source"] == "youtube")
assert out3["window"]["basis"] == "full_canonical_store" and out3["window"]["undated_records"] == 2
assert yt["coverage_state"] == "active_undated" and yt["undated_records"] == 2 and yt["undated_captured_30d"] == 1
assert "youtube" not in out3["expected_coverage"]["missing_or_stale_channels"]
assert out3["expected_coverage"]["active_undated_channels"] == ["youtube"]
assert [a["severity"] for a in out3["alerts"]] == ["P2"] and out3["state"] == "operational"
# an old undated record alone is still stale, and a truly absent channel is still P1
old_only = {"records": store["records"][:5] + [store["records"][6]]}
yt2 = next(c for c in build(window_only, old_only)["expected_coverage"]["channels"] if c["source"] == "youtube")
assert yt2["coverage_state"] == "present_stale"
assert "youtube" in build(window_only, {"records": store["records"][:5]})["expected_coverage"]["missing_or_stale_channels"]
print("PASS SRC-02 coverage over the full canonical store: undated records counted, not hidden")
