#!/usr/bin/env python3
"""Aggregate-only audit of private learning tables (options state entries,
outcomes, operator decisions).

Runs inside GitHub Actions where the Supabase service credentials already
exist. It never writes files under docs/ and never emits symbols, strikes,
expiries, prices, account ids, user ids, position ids, notes or reasons: only
counts and PASS/FAIL integrity checks, published as check-run annotations so
the audit is verifiable without sharing credentials.
"""
from __future__ import annotations
import json, os, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Every emitted key must be listed here; values must be int / bool / short enum strings.
ALLOWED_KEYS = {
    "credentials", "positions_total", "positions_by_status", "observations_total", "positions_observed",
    "state_entries", "consecutive_duplicate_states", "observations_unknown_position",
    "cross_account_mismatches", "observations_missing_account", "outcome_rows", "outcome_rows_mature",
    "outcome_positions_mature", "outcome_rows_duplicating_position", "decisions_total",
    "decisions_with_user_action", "decisions_attributed", "decisions_by_attribution",
    "check_account_isolation", "check_consecutive_dedup", "check_outcome_independence", "overall",
}
STATUS_ENUM = {"open", "pending_settlement", "closed", "expired", "assigned", "rolled", "exercised", "cancelled"}
ATTR_ENUM = {"pending", "system_error", "user_decision_error", "data_error", "market_randomness", "correct_process"}


def _id(v):
    return None if v is None or v == "" else str(v)


def summarize(positions, observations, outcomes, decisions):
    positions = list(positions or []); observations = list(observations or [])
    outcomes = list(outcomes or []); decisions = list(decisions or [])
    pos_by_id = {_id(p.get("id")): p for p in positions if _id(p.get("id"))}

    status = Counter()
    for p in positions:
        s = str(p.get("status") or "open")
        status[s if s in STATUS_ENUM else "other"] += 1

    by_pos = defaultdict(list)
    unknown_pos = mismatch = missing_acct = 0
    for o in observations:
        pid = _id(o.get("position_id"))
        by_pos[pid].append(o)
        pos = pos_by_id.get(pid)
        if pos is None:
            unknown_pos += 1
            continue
        pa, oa = _id(pos.get("broker_account_id")), _id(o.get("broker_account_id"))
        if pa and oa and pa != oa:
            mismatch += 1
        elif pa and not oa:
            missing_acct += 1

    consecutive_dup = 0
    entries = 0
    for rows in by_pos.values():
        rows = sorted(rows, key=lambda r: (str(r.get("observed_at") or ""), str(r.get("id") or "")))
        prev = None
        for r in rows:
            fp = r.get("state_fingerprint")
            if prev is not None and fp == prev:
                consecutive_dup += 1
            else:
                entries += 1
            prev = fp

    mature = [x for x in outcomes if x.get("outcome_mature") is True]
    mature_positions = {_id(x.get("position_id")) for x in mature if _id(x.get("position_id"))}

    attr = Counter()
    for d in decisions:
        a = str(d.get("attribution") or "pending")
        attr[a if a in ATTR_ENUM else "other"] += 1

    out = {
        "credentials": "configured",
        "positions_total": len(positions),
        "positions_by_status": dict(sorted(status.items())),
        "observations_total": len(observations),
        "positions_observed": len([k for k in by_pos if k]),
        "state_entries": entries,
        "consecutive_duplicate_states": consecutive_dup,
        "observations_unknown_position": unknown_pos,
        "cross_account_mismatches": mismatch,
        "observations_missing_account": missing_acct,
        "outcome_rows": len(outcomes),
        "outcome_rows_mature": len(mature),
        "outcome_positions_mature": len(mature_positions),
        # >0 means several state entries of one position share one final PnL:
        # statistics must weight by position, not by row.
        "outcome_rows_duplicating_position": max(0, len(mature) - len(mature_positions)),
        "decisions_total": len(decisions),
        "decisions_with_user_action": sum(1 for d in decisions if str(d.get("user_action") or "unrecorded") != "unrecorded"),
        "decisions_attributed": sum(1 for d in decisions if str(d.get("attribution") or "pending") != "pending"),
        "decisions_by_attribution": dict(sorted(attr.items())),
        "check_account_isolation": "PASS" if mismatch == 0 and unknown_pos == 0 else "FAIL",
        "check_consecutive_dedup": "PASS" if consecutive_dup == 0 else "FAIL",
        "check_outcome_independence": "PASS" if len(mature) == len(mature_positions) else "WARN",
    }
    out["overall"] = "PASS" if out["check_account_isolation"] == "PASS" and out["check_consecutive_dedup"] == "PASS" else "FAIL"
    assert_sanitized(out)
    return out


def assert_sanitized(out):
    extra = set(out) - ALLOWED_KEYS
    if extra:
        raise ValueError(f"unsanitized keys: {sorted(extra)}")
    for k, v in out.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                if kk not in STATUS_ENUM | ATTR_ENUM | {"other"} or not isinstance(vv, int):
                    raise ValueError(f"unsanitized nested value in {k}")
        elif not isinstance(v, (int, bool)) and v not in {"PASS", "FAIL", "WARN", "configured", "not_configured"}:
            raise ValueError(f"unsanitized value for {k}")


PUBLIC_KEYS = ("credentials", "check_account_isolation", "check_consecutive_dedup", "check_outcome_independence", "overall")


def public_view(out):
    """Annotations and step summaries are public on a public repo: PASS/FAIL only, no counts."""
    return {k: out[k] for k in PUBLIC_KEYS if k in out}


def annotation_lines(out):
    body = "PRIVATE_LEARNING_AUDIT " + json.dumps(public_view(out), sort_keys=True, separators=(",", ":"))
    lines = [f"::notice title=MyAlpha private learning audit (aggregate only)::{body}"]
    if out.get("overall") == "FAIL":
        failing = [k for k in ("check_account_isolation", "check_consecutive_dedup") if out.get(k) == "FAIL"]
        lines.append(f"::warning title=MyAlpha private learning audit::PRIVATE_AUDIT_FAILING {','.join(failing)}")
    return lines


def main():
    import server_action_engine as sa
    tables = {t: sa.supabase_rows(t) for t in
              ("options_positions", "option_learning_observations", "option_learning_outcomes", "operator_decisions")}
    if tables["options_positions"] is None:
        out = {"credentials": "not_configured", "overall": "not_configured"}
    else:
        out = summarize(tables["options_positions"], tables["option_learning_observations"],
                        tables["option_learning_outcomes"], tables["operator_decisions"])
    for line in annotation_lines(out):
        print(line)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Private learning audit (PASS/FAIL only)\n\n```json\n" + json.dumps(public_view(out), indent=2, sort_keys=True) + "\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
