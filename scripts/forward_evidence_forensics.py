#!/usr/bin/env python3
"""Read-only forensics for historical forward observations (2026-09-28 … 2026-10-08).

For every NYSE session it looks for *independent* contemporaneous evidence in the public repository:
a github-actions commit of docs/data.json whose trend_pulse is labelled with that session, committed
after the 16:00 ET close and before the next 09:30 ET open, and corroborated by GitHub-side workflow
runs (created_at is GitHub's own clock) on that exact commit. The signal content is then the
deterministic mapping of that committed input under the pinned rule (RULE_HASH), and the rule code
version is pinned by the git blob ids of the browser rule files at that commit.

It never edits history and never promotes anything. Output is an append-only list of *proposals*:
  A_pending_review : independent pre-open evidence binds content + data cutoff + rule version + time.
                     May apply for Genuine Forward status only through a separate reviewer entry.
  B                : inputs were published only intraday or after the next open (time-corroborated
                     historical observation, scored separately, never Genuine Forward).
  none             : no publication for that session (explicit GAP).
Browser (localStorage) rows are grade C by default; matching them against these reconstructions is a
separate private step and never changes a row's capture_mode.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, urllib.request
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_observation_engine as foe  # noqa: E402
import trading_calendar as tc  # noqa: E402

ET = ZoneInfo("America/New_York")
OUT = ROOT / "research" / "archive" / "forward_evidence_audit.jsonl"
RULE_FILES = ("docs/assets/decision-journal.js", "docs/assets/stock-watchlist.js", "docs/assets/investment-assistant.js")
PROPOSAL_VERSION = "forensics-1"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def data_commits(since, until):
    rows = []
    for line in git("log", "--reverse", "--format=%H|%cI|%an", f"--since={since}", f"--until={until}", "--", "docs/data.json").splitlines():
        h, t, a = line.split("|")
        try:
            d = json.loads(git("show", f"{h}:docs/data.json") or "{}")
        except json.JSONDecodeError:
            continue
        rows.append((h, datetime.fromisoformat(t).astimezone(timezone.utc), a, d))
    return rows


def session_of(d):
    tp = d.get("trend_pulse") or {}
    ds = sorted({str(v.get("date"))[:10] for v in tp.values() if isinstance(v, dict) and v.get("available") and v.get("date")})
    return ds[-1] if ds else None


def reconstruct(d, session):
    mi = d.get("market_indicators") or {}
    spx, ixic = (foe.num((mi.get(k) or {}).get("day_chg")) for k in ("spx", "ixic"))
    vix = foe.num((mi.get("vix") or {}).get("close"))
    mode, level = foe.market_mode(spx, ixic, vix)
    rows = []
    for sym, v in sorted((d.get("trend_pulse") or {}).items()):
        if not v.get("available") or str(v.get("date"))[:10] != session:
            continue
        st, sc = str(v.get("state") or ""), foe.num(v.get("score"))
        rows.append({"symbol": sym, "stage": st, "score": sc, "eligible": foe.eligible(mode, st, sc), "decision": foe.decision(st, mode)})
    return mode, level, rows


def github_runs(sha):
    tok, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY", "simonzixin8166-wq/quant-dashboard")
    if tok:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs?head_sha={sha}&per_page=10",
                                     headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "MyAlpha-Forensics"})
        with urllib.request.urlopen(req, timeout=20) as r:
            runs = json.loads(r.read().decode()).get("workflow_runs", [])
    else:  # local: gh CLI
        out = subprocess.run(["gh", "api", f"repos/{repo}/actions/runs?head_sha={sha}&per_page=10"], capture_output=True, text=True).stdout
        runs = json.loads(out or "{}").get("workflow_runs", [])
    return sorted(({"id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in runs), key=lambda r: r["created_at"])


def build(sessions, commits, runs_fn=github_runs, now=None):
    now = now or datetime.now(timezone.utc)
    by_session = {}
    for h, ct, author, d in commits:
        s = session_of(d)
        if s:
            by_session.setdefault(s, []).append((h, ct, author, d))
    out = []
    for s in sessions:
        sd = date.fromisoformat(s)
        close = datetime.combine(sd, time(16, 0), ET).astimezone(timezone.utc)
        nopen = foe.next_open_utc(sd)
        cands = by_session.get(s, [])
        phases = {"intraday": 0, "post_close_pre_open": 0, "after_next_open": 0}
        for _, ct, _, _ in cands:
            phases["intraday" if ct < close else "post_close_pre_open" if ct < nopen else "after_next_open"] += 1
        pre = [c for c in cands if close <= c[1] < nopen and c[2] == "github-actions"]
        entry = {"session": s, "proposal_version": PROPOSAL_VERSION, "rule_hash": foe.RULE_HASH,
                 "publication_phases": phases, "status": "proposed", "reviewer": "claude-proposal",
                 "created_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                 "close_utc": close.isoformat().replace("+00:00", "Z"), "next_open": nopen.isoformat().replace("+00:00", "Z"),
                 "matures": {str(h): tc.add_sessions(sd, h).isoformat() for h in foe.HORIZONS}}
        if pre:
            h, ct, author, d = pre[0]
            runs = runs_fn(h)
            corroborated = [r for r in runs if close.isoformat() <= r["created_at"].replace("Z", "+00:00") < nopen.isoformat()]
            mode, level, rows = reconstruct(d, s)
            entry.update({
                "proposed_grade": "A_pending_review" if corroborated else "B",
                "evidence": {"commit": h, "commit_time": ct.isoformat().replace("+00:00", "Z"), "author": author,
                             "github_runs_on_commit": corroborated or runs[:3],
                             "rule_file_blobs": {f: git("rev-parse", f"{h}:{f}").strip() or None for f in RULE_FILES}},
                "reconstruction": {"mode": mode, "level": level,
                                   "observations": rows, "eligible": [r["symbol"] for r in rows if r["eligible"]],
                                   "payload_sha": hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]},
            })
        elif cands:
            h, ct, author, d = cands[0]
            mode, level, rows = reconstruct(d, s)
            entry.update({"proposed_grade": "B", "evidence": {"commit": h, "commit_time": ct.isoformat().replace("+00:00", "Z"), "author": author,
                                                              "reason": "published only intraday or after the next session opened"},
                          "reconstruction": {"mode": mode, "level": level, "eligible": [r["symbol"] for r in rows if r["eligible"]]}})
        else:
            entry.update({"proposed_grade": "none", "evidence": None, "reason": "no publication for this session (explicit GAP)"})
        entry["audit_id"] = hashlib.sha256(f"{s}|{PROPOSAL_VERSION}|{foe.RULE_HASH}|{(entry.get('evidence') or {}).get('commit')}".encode()).hexdigest()[:20]
        out.append(entry)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-09-28")
    ap.add_argument("--end", default="2026-10-08")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    sessions = [d.isoformat() for d in tc.sessions_between(tc.previous_session(date.fromisoformat(a.start)), date.fromisoformat(a.end))]
    commits = data_commits(a.start, (date.fromisoformat(a.end) + (tc.next_session(date.fromisoformat(a.end)) - date.fromisoformat(a.end))).isoformat() + "T23:59")
    entries = build(sessions, commits)
    existing = set()
    if OUT.exists():
        existing = {json.loads(x)["audit_id"] for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()}
    new = [e for e in entries if e["audit_id"] not in existing]
    for e in entries:
        print(e["session"], e["proposed_grade"], (e.get("evidence") or {}).get("commit", "")[:9], len((e.get("reconstruction") or {}).get("eligible", [])))
    if a.write and new:
        with OUT.open("a", encoding="utf-8") as f:
            for e in new:
                f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
