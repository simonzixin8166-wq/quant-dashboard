#!/usr/bin/env python3
"""Skip a late *duplicate* US-close Daily (efficiency, #133 10/31; reminder: no trading logic here).

GitHub often starts the '30 21 * * 1-5' cron 3-4 hours late (~00:40-01:15Z). By then the Daily Guardian has
usually already published that NYSE session (~23:15-23:30Z), so the late run rebuilds the same session, rewrites
the heavy source files and re-triggers Server Action Watch / QA - and once (10/30) failed on its own and flipped
system_status to `attention`.

This gate runs only for that one cron. It answers skip=true only when ALL of these hold for the latest completed
NYSE session (trading_calendar.expected_latest_completed_session):
  * docs/data.json spy_date == session, and every core row with tiers has date == session
  * docs/research/server_action_status.json data_trust.ok is true and market_as_of == session
Anything else - missing/garbled files, an older session, a failed trust check, any exception - answers
skip=false, i.e. the Daily runs exactly as before (fail-open towards running). The 08:15Z A/HK snapshot,
workflow_dispatch (Guardian / manual) and push triggers never reach this gate.

    python scripts/daily_skip_gate.py            # prints skip=true|false and a reason; writes $GITHUB_OUTPUT
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar  # noqa: E402


def decide(data, server, session):
    """Pure decision: (skip: bool, reason: str). `session` is an ISO date string."""
    if not isinstance(data, dict) or not isinstance(server, dict):
        return False, "inputs_unavailable"
    if data.get("spy_date") != session:
        return False, f"not_published(spy_date={data.get('spy_date')}, expected={session})"
    core = data.get("core")
    rows = {s: r for s, r in (core or {}).items() if isinstance(r, dict) and r.get("tiers")}
    if not rows:
        return False, "core_rows_unavailable"
    stale = sorted(s for s, r in rows.items() if r.get("date") != session)
    if stale:
        return False, f"core_rows_stale({','.join(stale)})"
    trust = server.get("data_trust") if isinstance(server.get("data_trust"), dict) else {}
    if trust.get("ok") is not True:
        return False, "data_trust_not_ok"
    if trust.get("market_as_of") != session:
        return False, f"data_trust_session({trust.get('market_as_of')})"
    return True, f"already_published({session})"


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def main(now=None, root=ROOT):
    try:
        session = str(trading_calendar.expected_latest_completed_session(now or datetime.now(timezone.utc)))
        skip, reason = decide(load(root / "docs" / "data.json"),
                              load(root / "docs" / "research" / "server_action_status.json"), session)
    except Exception as exc:  # fail-open: run the Daily
        skip, reason = False, f"gate_error({type(exc).__name__})"
    line = f"skip={'true' if skip else 'false'}"
    print(f"{line} reason={reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{line}\nreason={reason}\n")
    return skip, reason


if __name__ == "__main__":
    main()
