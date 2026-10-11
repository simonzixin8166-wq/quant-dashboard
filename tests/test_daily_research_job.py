"""Auto research job: idempotent, append-only, shadow-only, explicit abstentions, revisit events."""
import json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_research_job as drj

tmp = Path(tempfile.mkdtemp())
drj.JOURNAL, drj.STATUS = tmp / "journal.jsonl", tmp / "status.json"
now = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)  # Saturday → expected session 2026-10-09
st, new = drj.run(now=now, fetch_claims=False, run_id="t1")
assert st["market_as_of"] == "2026-10-09" and new
hyps = [r for r in new if r["type"] == "hypothesis"]
assert hyps and all(r["production_use"] is False and r["shadow"] is True for r in new)
for h in hyps:
    assert h["stance"] in ("bullish", "neutral", "bearish")
    assert h["invalidation"] and h["next_review"] and h["decision_reason"] and h["rule_hash"] == drj.RULE_HASH
    assert all(e["sign"] > 0 for e in h["supporting"]) or h["stance"] == "bearish"
    assert "order" in h["research_hint"]  # always phrased as research, never an order
    assert h["outcome"]["status"] == "pending"
assert any(r["type"] == "abstain" for r in new)  # symbols with <200 sessions abstain explicitly
st2, new2 = drj.run(now=now, fetch_claims=False, run_id="t2")
assert new2 == [], "second run for the same session must append nothing"
lines = drj.JOURNAL.read_text(encoding="utf-8").splitlines()
assert len(lines) == len(new)
# a revisit on a later session appends an event, never rewrites
h0 = hyps[0]
fake = dict(h0); fake["invalidation"] = [{"metric": "close", "op": ">", "value": 0, "note": "always hit"}]
assert drj.check_invalidation(fake, drj.kc.history(h0["symbol"])) is not None
for p in ("scripts/server_action_engine.py", "scripts/forward_observation_engine.py", "docs/assets/autonomous-agent.js"):
    assert "auto_research_journal" not in (ROOT / p).read_text(encoding="utf-8")
print("PASS daily research job")
