"""Issue #134 regression: Server Action snapshot must follow the published market session.

Covers stale/fresh market, stale/fresh prior snapshot, missing private credentials,
missing snapshot, idempotent re-runs and public-output privacy. No network, no real
positions or secrets are used: Supabase, quotes, events and ledgers are stubbed.
"""
from __future__ import annotations
import importlib.util, json, os, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

for k in ("MYALPHA_TG_BOT_TOKEN", "MYALPHA_TG_CHAT_ID", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.pop(k, None)

spec = importlib.util.spec_from_file_location("sa_fresh", ROOT / "scripts" / "server_action_engine.py")
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)
import private_guardrail as guard  # noqa: E402

EXPECTED = date(2026, 10, 7)
QUOTE = {"underlyingPrice": [120], "bid": [1], "ask": [1.05], "mid": [1.02], "delta": [-.1],
         "updated": [datetime.now(timezone.utc).timestamp()]}
PRIVATE_POSITION = {
    "id": 9001, "symbol": "ZZPRIVATE", "opt_type": "put", "side": "short", "strike": 100,
    "expiry": "2099-12-31", "status": "open", "broker_account_id": 424242,
    "account_number": "U-SECRET-77", "user_id": "00000000-private-user",
}


def setup(tmp: Path, *, spy_date: str, overall: str = "running", credentials: bool = True,
          positions=None, previous=None):
    data = tmp / "data.json"
    system = tmp / "system_status.json"
    out = tmp / "server_action_status.json"
    data.write_text(json.dumps({"spy_date": spy_date}), encoding="utf-8")
    system.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "decision_data_contract": {"excluded_artifacts": []},
        "resource_guard": {"mode": "normal"},
    }), encoding="utf-8")
    if previous is not None:
        out.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif out.exists():
        out.unlink()
    sa.DATA, sa.SYSTEM, sa.PUBLIC_OUT = data, system, out
    sa.trading_calendar.expected_latest_completed_session = lambda now=None: EXPECTED
    rows = {"options_positions": list(positions or [])}
    sa.supabase_rows = (lambda table: rows.get(table, [])) if credentials else (lambda table: None)
    sa.edge_quote = lambda occ: QUOTE
    sa.upcoming_events = lambda hours=48: []
    sa.write_usage_ledger = lambda rows: False
    sa.write_option_learning_observations = lambda rows: True
    return out


def run(tmp: Path, **kw):
    out = setup(tmp, **kw)
    assert sa.main() == 0
    return out, json.loads(out.read_text(encoding="utf-8"))


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)

    # 1. Market still on the prior session: never a judgment.
    _, snap = run(tmp, spy_date="2026-10-06")
    assert snap["status"] == "cannot_judge", snap
    assert snap["judgment_basis"] == "market_data_stale", snap
    assert snap["data_trust"]["ok"] is False
    assert snap["data_trust"]["market_as_of"] == "2026-10-06"
    stale_snapshot = snap

    # 2. Snapshot missing entirely + fresh market: a new snapshot is produced and evaluated.
    out, snap = run(tmp, spy_date="2026-10-07")
    assert out.exists()
    assert snap["status"] == "clear" and snap["judgment_basis"] == "evaluated", snap
    assert snap["data_trust"]["ok"] is True and snap["data_trust"]["market_as_of"] == "2026-10-07"

    # 3. Stale prior snapshot written minutes ago must not suppress the fresh judgment.
    stale_snapshot = dict(stale_snapshot, last_checked_at=datetime.now(timezone.utc).isoformat())
    _, snap = run(tmp, spy_date="2026-10-07", previous=stale_snapshot)
    assert snap["status"] == "clear", snap
    assert snap["data_trust"]["market_as_of"] == "2026-10-07"
    assert snap["alert_fingerprint"] != stale_snapshot["alert_fingerprint"]

    # 4. Fresh prior snapshot + still-fresh market: next run is idempotent (byte-identical).
    out, first = run(tmp, spy_date="2026-10-07")
    before = out.read_text(encoding="utf-8")
    _, second = run(tmp, spy_date="2026-10-07", previous=first)
    assert out.read_text(encoding="utf-8") == before, "idempotent re-run must not rewrite the snapshot"

    # 5. Fresh market but no private credentials: explicit not-configured, never a fabricated decision.
    _, snap = run(tmp, spy_date="2026-10-07", credentials=False)
    assert snap["status"] == "cannot_judge", snap
    assert snap["judgment_basis"] == "credentials_not_configured", snap
    assert snap["positions_checked"] == 0
    assert snap["action_counts"] == {"l3": 0, "l2": 0, "unknown": 0, "thesis_review": 0}

    # 6. Fresh market but untrusted system status: still fail-closed with its own reason.
    _, snap = run(tmp, spy_date="2026-10-07", overall="attention")
    assert snap["status"] == "cannot_judge" and snap["judgment_basis"] == "system_status_untrusted", snap

    # 7. Credentials missing AND market stale: credentials reason wins (nothing was evaluated).
    _, snap = run(tmp, spy_date="2026-10-06", credentials=False)
    assert snap["judgment_basis"] == "credentials_not_configured", snap

    # 8. Privacy: a real-looking private position is evaluated but never reaches the public file.
    out, snap = run(tmp, spy_date="2026-10-07", positions=[PRIVATE_POSITION])
    text = out.read_text(encoding="utf-8")
    assert snap["positions_checked"] == 1 and snap["status"] == "clear", snap
    for secret in ("ZZPRIVATE", "424242", "U-SECRET-77", "private-user", "broker_account_id", "account_number"):
        assert secret not in text, secret
    allowed = guard.PUBLIC_JSON_ROOT_ALLOWLIST["docs/research/server_action_status.json"]
    assert set(snap) <= allowed, sorted(set(snap) - allowed)
    assert not guard.FORBIDDEN_KEYS.search(text)

# 9. judgment_basis unit contract.
jb = sa.judgment_basis
fresh = {"ok": True, "market_as_of": "2026-10-07", "expected_market_date": "2026-10-07"}
assert jb(fresh) == "evaluated"
assert jb(fresh, actions=[{"level": "unknown"}]) == "position_quote_unknown"
assert jb({**fresh, "market_as_of": None, "ok": False}) == "market_data_stale"
assert jb(fresh, credentials_configured=False) == "credentials_not_configured"

# 10. Workflow/QA contracts: refresh follows Daily success; QA demands a current server snapshot.
wf = (ROOT / ".github" / "workflows" / "server-action-watch.yml").read_text(encoding="utf-8")
assert 'workflows: ["Daily Dashboard Update"]' in wf
assert "github.event.workflow_run.conclusion == 'success'" in wf
assert "test_server_action_snapshot_freshness.py" in wf
qa_wf = (ROOT / ".github" / "workflows" / "autonomous-qa.yml").read_text(encoding="utf-8")
assert '"Server Action Watch"' in qa_wf
qa = (ROOT / "scripts" / "autonomous_site_qa.mjs").read_text(encoding="utf-8")
assert "serverMarketAsOf===expected" in qa and "&&serverCurrent" in qa

# Privacy minimisation: private-derived counts are presence-only in the public snapshot.
assert sa.presence(0) == 0 and sa.presence(3) == 1 and sa.presence(None) == 0
assert sa.presence_map({"persisted": 7, "attributed": 0}, ("persisted", "with_user_action", "attributed")) == {"persisted": 1, "with_user_action": 0, "attributed": 0}
print("PASS Issue #134 server action snapshot freshness / fail-closed / privacy")
