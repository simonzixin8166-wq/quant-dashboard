#!/usr/bin/env python3
"""Per-candidate review checklist for the 2026-09-29 … 2026-10-08 forward sessions (#133 6106619625).

For every session/symbol it rebuilds the observation from the data.json blob committed before the next
open (forensics-2 evidence), twice, and records a machine-reproducible checklist:
input commit + data.json blob + data as_of, rule-file blobs, publication time vs next open, payload and
its hash (determinism), market mode and whether the call is mode-invariant (intraday vs close mode),
eligible flag and whether the browser's top-N cap could have excluded it, entry-price basis, dependence
on private/intraday data, and whether any contemporaneous signal content exists independently.

It only proposes a class; it never approves or promotes. Output is append-only.
  proposed_class
    already_server_forward              : the session already has server_daily observations captured
                                          before the next open (genuine forward ledger) — nothing to promote
    historically_attested_reconstruction: same-input reproduction before the next open, no future data,
                                          but no independently saved contemporaneous signal content
    needs_evidence                      : a residual dependency (intraday mode / top-N / missing close)
                                          could have changed the browser's signal for this candidate
APPROVED can only be written by an independent reviewer (separate append-only entry).
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_observation_engine as foe  # noqa: E402

AUDIT = ROOT / "research" / "archive" / "forward_evidence_audit.jsonl"
LEDGER = ROOT / "research" / "archive" / "forward_observations.jsonl"
OUT = ROOT / "research" / "archive" / "forward_candidate_review.jsonl"
VERSION = "candidate-review-1"
SESSIONS = ("2026-09-29", "2026-09-30", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08")


def git_blob(blob):
    return subprocess.run(["git", "cat-file", "-p", blob], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def latest(entries, version, session):
    xs = [e for e in entries if e.get("session") == session and e.get("proposal_version") == version]
    return xs[-1] if xs else None


def mode_invariant(stage, score):
    return (foe.eligible("fear", stage, score) == foe.eligible("normal", stage, score)
            and foe.decision(stage, "fear") == foe.decision(stage, "normal"))


def mode_margin(data):
    """Distance of the close-based inputs to the nearest 'fear/watch' threshold (reviewer aid: a small
    margin means an intraday reading could plausibly have flipped the browser's mode)."""
    mi = data.get("market_indicators") or {}
    spx, ixic = (foe.num((mi.get(k) or {}).get("day_chg")) for k in ("spx", "ixic"))
    vix = foe.num((mi.get("vix") or {}).get("close"))
    m = {}
    if spx is not None: m["spx_pct_to_-1.25%"] = round((spx + 0.0125) * 100, 2)
    if ixic is not None: m["ixic_pct_to_-1.5%"] = round((ixic + 0.015) * 100, 2)
    if vix is not None: m["vix_pts_to_25"] = round(25 - vix, 2)
    return m


def review_session(session, forensics, equivalence, server_sessions, data):
    ev = forensics["evidence"]
    commit_time = datetime.fromisoformat(ev["commit_time"].replace("Z", "+00:00"))
    rows1, why = foe.build_observations(data, now_utc=commit_time, source_sha=ev["commit"])
    rows2, _ = foe.build_observations(data, now_utc=commit_time, source_sha=ev["commit"])
    deterministic = [r["payload_sha"] for r in rows1] == [r["payload_sha"] for r in rows2]
    cap = (equivalence or {}).get("candidate_cap") or 6
    n_eligible = sum(1 for r in rows1 if r["payload"]["eligible"])
    tp = data.get("trend_pulse") or {}
    out = []
    for r in rows1:
        p = r["payload"]
        inv = mode_invariant(p["stage"], p["score"])
        topn_risk = p["eligible"] and n_eligible > cap
        deps = []
        if not inv:
            deps.append("intraday_market_mode")
        if topn_risk:
            deps.append("browser_top_n_private_ranking")
        if p["close"] is None:
            deps.append("entry_close_missing")
        if session in server_sessions:
            cls = "already_server_forward"
        elif deps:
            cls = "needs_evidence"
        else:
            cls = "historically_attested_reconstruction"
        out.append({
            "kind": "forward_candidate_review", "review_version": VERSION, "session": session, "symbol": r["symbol"],
            "input": {"commit": ev["commit"], "data_json_blob": ev.get("data_json_blob"),
                      "data_as_of": str((tp.get(r["symbol"]) or {}).get("date"))[:10], "market_as_of": r["market_as_of"]},
            "rule_file_blobs": ev.get("rule_file_blobs"), "rule_equivalence": {
                "audit_id": (equivalence or {}).get("audit_id"), "grid_cases": (equivalence or {}).get("grid_cases"),
                "diff_count": (equivalence or {}).get("diff_count")},
            "published_at": ev["commit_time"], "next_open": forensics["next_open"],
            "locked_before_next_open": commit_time < datetime.fromisoformat(forensics["next_open"].replace("Z", "+00:00")),
            "github_runs_on_commit": [x.get("id") for x in ev.get("github_runs_on_commit") or []],
            "reconstructed_payload": p, "reconstructed_payload_sha": r["payload_sha"], "deterministic_rerun": deterministic,
            "market_mode": r["market"]["mode"], "mode_margin": mode_margin(data), "mode_basis": "daily close change (browser used intraday quotes)",
            "mode_invariant": inv,
            "eligible": p["eligible"], "eligible_in_session": n_eligible, "browser_cap": cap,
            "top_n_could_exclude": topn_risk,
            "entry_price_basis": "data.json close of the session in the committed blob (browser used dailyClose feed)",
            "future_information": "none: every input is from a blob committed before the next open",
            "contemporaneous_signal_content": "none independently saved (browser rows were localStorage, uploaded later; private match is a separate enum-only step)",
            "residual_dependencies": deps, "proposed_class": cls, "approved": False,
            "reviewer": "claude-tool (proposal only; APPROVED requires an independent reviewer entry)",
            "matures": r["matures"],
        })
    return out, why, deterministic


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    entries = [json.loads(x) for x in AUDIT.read_text(encoding="utf-8").splitlines() if x.strip()]
    server_sessions = {json.loads(x)["session"] for x in LEDGER.read_text(encoding="utf-8").splitlines()
                       if x.strip() and json.loads(x).get("attested_forward") and json.loads(x).get("capture") == "server_daily"}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rows, summary = [], {}
    for s in SESSIONS:
        f = latest(entries, "forensics-2", s)
        eq = latest(entries, "rule-equivalence-1", s)
        if not f or not (f.get("evidence") or {}).get("data_json_blob"):
            summary[s] = {"error": "no forensics-2 evidence"}
            continue
        data = json.loads(git_blob(f["evidence"]["data_json_blob"]))
        out, why, det = review_session(s, f, eq, server_sessions, data)
        for o in out:
            o["created_at"] = now
            o["review_id"] = hashlib.sha256(f"{s}|{o['symbol']}|{VERSION}|{o['reconstructed_payload_sha']}".encode()).hexdigest()[:20]
        rows += out
        cnt = {}
        for o in out:
            cnt[o["proposed_class"]] = cnt.get(o["proposed_class"], 0) + 1
        summary[s] = {"mode_margin": mode_margin(data), "candidates": len(out), "eligible": sum(o["eligible"] for o in out), "deterministic": det, **cnt}
    tot = {}
    for o in rows:
        tot[o["proposed_class"]] = tot.get(o["proposed_class"], 0) + 1
    print(json.dumps({"sessions": summary, "total": tot, "approved": 0}, ensure_ascii=False))
    if a.write:
        have = set()
        if OUT.exists():
            have = {json.loads(x)["review_id"] for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()}
        new = [o for o in rows if o["review_id"] not in have]
        with OUT.open("a", encoding="utf-8") as fh:
            for o in new:
                fh.write(json.dumps(o, ensure_ascii=False, sort_keys=True) + "\n")
        print(json.dumps({"appended": len(new)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
