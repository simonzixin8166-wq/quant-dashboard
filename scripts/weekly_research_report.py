#!/usr/bin/env python3
"""Weekly automatic research report (#133 6109444028 P0-C3). Free; public data only.

Summarises the trailing five NYSE sessions of research/knowledge/auto_research_journal.jsonl:
new hypotheses (by stance), revisits by status (still valid / invalidated / superseded / review due),
abstentions and why, timing-integrity flags, fundamentals availability, pending maturities, source
failures, plus GitHub Actions minutes actually used in the last 7 days (from the Actions API).
Outcomes are reported only when matured; nothing is dressed up as returns before then.
Output: docs/research/weekly_research_report.json
"""
from __future__ import annotations
import json, os, sys, urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

JOURNAL = ROOT / "research" / "knowledge" / "auto_research_journal.jsonl"
STATUS = ROOT / "docs" / "research" / "auto_research_status.json"
OUT = ROOT / "docs" / "research" / "weekly_research_report.json"


def actions_minutes(since):
    tok, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not tok or not repo:
        return {"status": "unavailable (no token in this context)"}
    total, runs, page = 0.0, 0, 1
    by = Counter()
    while page <= 10:
        url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&page={page}&created=>={since}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "MyAlpha-Weekly"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
        except Exception as e:
            return {"status": f"unavailable ({type(e).__name__})"}
        items = data.get("workflow_runs") or []
        for x in items:
            if x.get("run_started_at") and x.get("updated_at"):
                m = (datetime.fromisoformat(x["updated_at"].replace("Z", "+00:00")) -
                     datetime.fromisoformat(x["run_started_at"].replace("Z", "+00:00"))).total_seconds() / 60
                total += max(m, 0); runs += 1; by[x.get("name")] += max(m, 0)
        if len(items) < 100:
            break
        page += 1
    return {"runs": runs, "wall_minutes_approx": round(total, 1), "top_workflows": {k: round(v, 1) for k, v in by.most_common(6)},
            "note": "wall-clock minutes from run start to last update; public-repo Actions minutes are free, but schedules can be throttled"}


def build(now=None):
    now = now or datetime.now(timezone.utc)
    rows = [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()] if JOURNAL.exists() else []
    end = tc.expected_latest_completed_session(now)
    start = tc.add_sessions(end, -4)
    week = [r for r in rows if start.isoformat() <= r.get("market_as_of", "") <= end.isoformat()]
    # One research judgment per (symbol, session) and one revisit per (hypothesis, session): when a generator
    # upgrade re-runs a session, its regenerated hypotheses / repeated revisits and 'generator upgrade'
    # supersedes are engineering events, reported separately, never extra research (#133, 2026-10-13).
    gen_rank = lambda r: (r.get("generated_at") or "")
    eng = [r for r in week if r["type"] == "revisit" and str((r.get("trigger") or {}).get("reason", "")).startswith("generator upgrade")]
    _h = {}
    for r in sorted((r for r in week if r["type"] == "hypothesis"), key=gen_rank):
        _h[(r["symbol"], r["market_as_of"])] = r
    hyps = list(_h.values())
    _rv = {}
    for r in sorted((r for r in week if r["type"] == "revisit" and r not in eng), key=gen_rank):
        _rv.setdefault((r.get("hypothesis_id"), r["market_as_of"]), r)
    rev = list(_rv.values())
    regenerated = sum(1 for r in week if r["type"] == "hypothesis") - len(hyps)
    repeated_revisits = sum(1 for r in week if r["type"] == "revisit") - len(eng) - len(rev)
    abst = [r for r in week if r["type"] == "abstain"]
    sessions_seen = sorted({r["market_as_of"] for r in week if r["type"] in ("hypothesis", "revisit", "abstain")})
    expected = [start.isoformat()] + [d.isoformat() for d in tc.sessions_between(start, end) if d != start]
    first = min((r["market_as_of"] for r in rows if r["type"] in ("hypothesis", "abstain")), default=None)
    pending = [r for r in rows if r["type"] == "hypothesis" and (r.get("outcome") or {}).get("status") == "pending"]
    st = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    return {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "window": {"from_session": start.isoformat(), "to_session": end.isoformat(), "sessions_expected": expected,
                   "sessions_with_research": sessions_seen,
                   "before_job_existed": [d for d in expected if first is None or d < first],
                   "gaps": [d for d in expected if first is not None and d >= first and d not in sessions_seen]},
        "new_hypotheses": {"count": len(hyps), "by_stance": dict(Counter(r["stance"] for r in hyps))},
        "revisits": dict(Counter(r["status"] for r in rev)),
        "engineering_reruns": {"generator_upgrade_supersedes": len(eng), "regenerated_hypotheses": regenerated,
                               "repeated_revisits": repeated_revisits,
                               "note": "same-session generator re-runs; excluded from hypothesis and revisit counts"},
        "invalidated": [{"symbol": r["symbol"], "hypothesis": r["hypothesis_id"], "trigger": (r.get("trigger") or {}).get("note")}
                        for r in rev if r["status"] == "invalidated"],
        "abstentions": {"count": len(abst), "reasons": dict(Counter(r["decision_reason"].split(":")[0] for r in abst))},
        "timing_flags": {"records_with_late_or_unknown_inputs": sum(1 for r in hyps if not (r.get("timing_check") or {}).get("all_inputs_available_before_lock", True)),
                         "records_using_post_close_inputs": sum(1 for r in hyps if (r.get("timing_check") or {}).get("inputs_after_market_close"))},
        "fundamentals": {"with_sec_facts": sum(1 for r in hyps if (r.get("fundamentals") or {}).get("available")),
                         "without": sum(1 for r in hyps if not (r.get("fundamentals") or {}).get("available"))},
        "source_status": {k: v.get("status", "ok") for k, v in (st.get("inputs") or {}).items()},
        "maturity": {"pending_hypotheses": len(pending), "earliest_maturity": min(((r.get("outcome") or {}).get("matures") for r in pending), default=None),
                     "matured": 0, "note": "no outcome or return is reported before maturity"},
        "actions_usage_7d": actions_minutes((now - timedelta(days=7)).date().isoformat()),
        "learning_state": "UNPROVEN", "production_use": False,
    }


def main():
    rep = build()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=Weekly research report::window {rep['window']['from_session']}..{rep['window']['to_session']} "
          f"hypotheses={rep['new_hypotheses']['count']} revisits={sum(rep['revisits'].values())} gaps={len(rep['window']['gaps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
