"""Private learning audit emits aggregates only and detects integrity problems."""
from __future__ import annotations
import json
import importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pla", ROOT / "scripts" / "private_learning_audit.py")
pla = importlib.util.module_from_spec(spec); spec.loader.exec_module(pla)

SECRETS = ("ZZSYM", "U-ACCT-9", "user-uuid-1", "77.5", "2099-12-31", "secret note", "9001", "4242")
positions = [
    {"id": 9001, "symbol": "ZZSYM", "strike": 77.5, "expiry": "2099-12-31", "status": "open", "broker_account_id": 4242, "user_id": "user-uuid-1"},
    {"id": 9002, "symbol": "ZZSYM", "strike": 80, "expiry": "2099-12-31", "status": "closed", "broker_account_id": 5353},
]
def obs(i, pid, fp, acct, t):
    return {"id": i, "position_id": pid, "state_fingerprint": fp, "broker_account_id": acct, "observed_at": t,
            "symbol": "ZZSYM", "risk_reason": "secret note", "user_id": "user-uuid-1"}
clean = [obs(1, 9001, "a", 4242, "2026-10-06T00:00Z"), obs(2, 9001, "b", 4242, "2026-10-07T00:00Z"),
         obs(3, 9001, "a", 4242, "2026-10-08T00:00Z"),  # re-entry to an earlier state is a new state entry
         obs(4, 9002, "c", 5353, "2026-10-06T00:00Z")]
outcomes = [{"position_id": 9002, "outcome_mature": True, "realized_pnl": 123.4},
            {"position_id": 9001, "outcome_mature": False}]
decisions = [{"decision": "x", "reason": "secret note", "user_action": "executed", "attribution": "correct_process"},
             {"decision": "y", "user_action": "unrecorded", "attribution": "pending"}]

out = pla.summarize(positions, clean, outcomes, decisions)
assert out["overall"] == "PASS" and out["state_entries"] == 4 and out["consecutive_duplicate_states"] == 0
assert out["check_account_isolation"] == "PASS" and out["check_outcome_independence"] == "PASS"
assert out["positions_by_status"] == {"closed": 1, "open": 1}
assert out["decisions_with_user_action"] == 1 and out["decisions_attributed"] == 1
text = "\n".join(pla.annotation_lines(out))
for s in SECRETS:
    assert s not in text, s
assert text.startswith("::notice title=MyAlpha private learning audit (aggregate only)::PRIVATE_LEARNING_AUDIT {")
# Public annotations carry PASS/FAIL only: no counts that could reveal private positions/decisions.
pub = json.loads(text.split("PRIVATE_LEARNING_AUDIT ", 1)[1].split("\n")[0])
assert set(pub) <= set(pla.PUBLIC_KEYS) and not any(isinstance(v, int) for v in pub.values()), pub

# Consecutive duplicate state (daily delta noise recorded as a new sample) is detected.
dup = clean + [obs(5, 9001, "a", 4242, "2026-10-09T00:00Z")]
out = pla.summarize(positions, dup, outcomes, decisions)
assert out["consecutive_duplicate_states"] == 1 and out["check_consecutive_dedup"] == "FAIL" and out["overall"] == "FAIL"
assert "PRIVATE_AUDIT_FAILING check_consecutive_dedup" in pla.annotation_lines(out)[-1]

# Cross-account contamination (same position observed under another account) is detected.
bad = clean + [obs(6, 9002, "d", 4242, "2026-10-09T00:00Z")]
out = pla.summarize(positions, bad, outcomes, decisions)
assert out["cross_account_mismatches"] == 1 and out["check_account_isolation"] == "FAIL"

# Several state entries sharing one final PnL are flagged so statistics weight by position.
multi = [{"position_id": 9001, "outcome_mature": True}, {"position_id": 9001, "outcome_mature": True}]
out = pla.summarize(positions, clean, multi, decisions)
assert out["outcome_rows_duplicating_position"] == 1 and out["check_outcome_independence"] == "WARN"

# The sanitizer refuses anything outside the allowlist.
try:
    pla.assert_sanitized({"overall": "PASS", "symbol": "ZZSYM"}); raise AssertionError("must refuse")
except ValueError:
    pass

# Never writes public artifacts.
src = (ROOT / "scripts" / "private_learning_audit.py").read_text(encoding="utf-8")
assert "docs/" not in src.split('"""', 2)[2].replace("never writes files under docs/", "")
wf = (ROOT / ".github" / "workflows" / "server-action-watch.yml").read_text(encoding="utf-8")
assert "python scripts/private_learning_audit.py" in wf and "continue-on-error: true" in wf
print("PASS private learning audit: aggregate-only, isolation/dedup/independence checks")
