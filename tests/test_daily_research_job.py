"""Auto research job v2: idempotent, append-only, shadow-only, timing integrity, SEC facts, legacy annotation."""
import json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_research_job as drj

tmp = Path(tempfile.mkdtemp())
drj.JOURNAL, drj.STATUS = tmp / "journal.jsonl", tmp / "status.json"
# synthetic SEC fact file (AVGO filed before lock; NVDA filed AFTER lock → must be excluded)
sec = {"generated_at": "2026-10-10T00:00:00Z", "symbols": {
    "AVGO": {"available": True, "cik": "0001730168", "entity": "Broadcom Inc.", "revenue_concept": "Revenues",
             "revenue_q": {"val": 16e9, "start": "2026-05-04", "end": "2026-08-02", "fy": 2026, "fp": "Q3", "form": "10-Q", "filed": "2026-09-10", "accn": "x"},
             "revenue_yoy": 0.22, "net_income_q": {"val": 4e9, "end": "2026-08-02", "form": "10-Q", "filed": "2026-09-10", "accn": "x"}},
    "NVDA": {"available": True, "cik": "1", "entity": "NVIDIA", "revenue_concept": "Revenues",
             "revenue_q": {"val": 50e9, "start": "2026-07-01", "end": "2026-09-30", "fy": 2027, "fp": "Q3", "form": "10-Q", "filed": "2026-10-20", "accn": "y"},
             "revenue_yoy": 0.5},
    "IREN": {"available": False, "reason": "no 3-month USD revenue facts in us-gaap"}}}
drj.SEC = tmp / "sec.json"; drj.SEC.write_text(json.dumps(sec))
now = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)  # Saturday → expected session 2026-10-09
st, new = drj.run(now=now, fetch_claims=False, run_id="t1")
assert st["market_as_of"] == "2026-10-09" and new
hyps = {r["symbol"]: r for r in new if r["type"] == "hypothesis"}
for h in hyps.values():
    assert h["production_use"] is False and h["shadow"] is True and h["forward_eligible"] is False
    assert h["research_date"] == "2026-10-10" and h["market_as_of"] == "2026-10-09" and h["lock_at"] == h["generated_at"]
    assert h["timing_check"]["all_inputs_available_before_lock"] in (True, False)
    assert h["invalidation"] and h["next_review"] and "order" in h["research_hint"] and h["outcome"]["status"] == "pending"
    if not h["opposing"]:
        assert h["opposing_note"] and "not evidence that no risk exists" in h["opposing_note"]["why_empty"]
a = hyps["AVGO"]
assert a["fundamentals"]["available"] and any(e["name"] == "sec_revenue_yoy" and e["sign"] == 1 for e in a["supporting"] + a["opposing"])
assert hyps["NVDA"]["fundamentals"]["available"] is False and "after the lock time" in hyps["NVDA"]["fundamentals"]["reason"]
assert hyps["IREN"]["fundamentals"]["available"] is False and "SEC financial facts unavailable" in hyps["IREN"]["unknowns"]
assert any(r["type"] == "abstain" for r in new)
# timing: an input that became available after the lock is reported, never silently used as 'before lock'
tc = drj.timing_check({"fred_macro": {"sha256": "x", "available_at": "2026-10-11T00:00:00Z"}}, [], "2026-10-09", "2026-10-10T15:00:00Z")
assert tc["late_inputs"] == ["fred_macro"] and not tc["all_inputs_available_before_lock"]
tc2 = drj.timing_check({"fred_macro": {"sha256": "x"}}, [{"record_id": "r", "published_at": None}], "2026-10-09", "2026-10-10T15:00:00Z")
assert "fred_macro" in tc2["unknown_timestamps"] and "claim:r" in tc2["unknown_timestamps"]
tc3 = drj.timing_check({}, [{"record_id": "r2", "first_seen": "2026-10-10T02:00:00Z"}], "2026-10-09", "2026-10-10T15:00:00Z")
assert "claim:r2" in tc3["inputs_after_market_close"]  # delayed collection after the close
# duplicate author claims never add weight
d = drj.dedupe_claims([{"author": "a", "symbol": "X", "stance": "hold", "sentence_sha256": "s", "published_at": "2026-10-01"}] * 3)
assert len(d) == 1
# repeated run for the same session appends nothing
st2, new2 = drj.run(now=now, fetch_claims=False, run_id="t2")
assert new2 == []
# legacy v1 records get exactly one append-only annotation
legacy = {"type": "hypothesis", "record_id": "X-2026-10-09-h", "symbol": "X", "market_as_of": "2026-10-09",
          "generator_version": "auto-research-1", "generated_at": "2026-10-11T13:00:00Z", "run_id": "38142086034"}
ann = drj.annotate_legacy([legacy], "2026-10-11T14:00:00Z", "t3")
assert len(ann) == 1 and "not a signal locked" in ann[0]["note"] and ann[0]["forward_eligible"] is False
assert drj.annotate_legacy([legacy] + ann, "2026-10-11T14:00:00Z", "t4") == []
fake = dict(a); fake["invalidation"] = [{"metric": "close", "op": ">", "value": 0, "note": "always hit"}]
assert drj.check_invalidation(fake, drj.kc.history("AVGO")) is not None
for p in ("scripts/server_action_engine.py", "scripts/forward_observation_engine.py", "docs/assets/autonomous-agent.js"):
    assert "auto_research_journal" not in (ROOT / p).read_text(encoding="utf-8")
print("PASS daily research job v2")
import weekly_research_report as wr
wr.JOURNAL, wr.STATUS = drj.JOURNAL, drj.STATUS
rep = wr.build(now)
assert rep["window"]["to_session"] == "2026-10-09" and rep["maturity"]["matured"] == 0 and rep["learning_state"] == "UNPROVEN"
assert "2026-10-05" in rep["window"]["before_job_existed"] and rep["window"]["gaps"] == []
print("PASS weekly report")
bad = {"type": "hypothesis", "record_id": "AVGO-x-h", "symbol": "AVGO", "market_as_of": "2026-10-09",
       "fundamentals": {"available": True, "revenue_q": {"end": "2026-08-02"}, "net_income_q": {"end": "2019-08-04"}}}
c = drj.annotate_sec_corrections([bad], {}, "2026-10-12T00:00:00Z", "t5")
assert len(c) == 1 and "mixed" in c[0]["issues"][0] and c[0]["kind"] == "sec_correction"
assert drj.annotate_sec_corrections([bad] + c, {}, "2026-10-12T00:00:00Z", "t6") == []
stale = {"type": "hypothesis", "record_id": "NVDA-x-h", "symbol": "NVDA", "market_as_of": "2026-10-09",
         "fundamentals": {"available": True, "revenue_q": {"end": "2022-01-30"}}}
assert "stale" in " ".join(drj.annotate_sec_corrections([stale], {}, "2026-10-12T00:00:00Z", "t7")[0]["issues"])
print("PASS sec corrections")
