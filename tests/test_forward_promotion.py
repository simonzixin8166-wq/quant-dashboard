"""Owner promotion: separate ledger, never attested_forward, never merged into live counts, append-only."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_promotion as fp
import forward_observation_engine as foe

rows = [json.loads(x) for x in fp.REVIEW.read_text(encoding="utf-8").splitlines() if x.strip()]
approvals, promoted = fp.build(rows)
assert {a["session"] for a in approvals} == set(fp.SESSIONS) and "2026-10-08" not in {p["session"] for p in promoted}
assert all(p["capture"] == "owner_approved_reconstruction" and p["promoted"] and p["attested_forward"] is False for p in promoted)
assert all(a["approver"] == "owner" and a["reported_separately_from_live"] for a in approvals)
# review file untouched: tool proposals stay approved=false
assert all(r["approved"] is False for r in rows)
live = foe.read_ledger()
st = foe.status(live, promoted_rows=foe.read_promoted())
assert st["observations"] == len(live) and st["attested_observations"] <= len(live)  # promoted not in live counts
if st["promoted"]:
    assert st["promoted"]["observations"] == len(foe.read_promoted())
assert all(not r.get("promoted") for r in live)
print("PASS forward promotion")
