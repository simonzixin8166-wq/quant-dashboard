#!/usr/bin/env python3
"""Run one V6.15 research step under a per-step production hash invariant."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from research_boundary_guard import snapshot, assert_allowed, git_worktree_paths, check_evidence_lock

AUDIT=ROOT/"research"/"audit"/"step_boundary_log.json"

def snapshot_digest(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    import hashlib
    return hashlib.sha256(raw).hexdigest()

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--name",required=True)
    ap.add_argument("command",nargs=argparse.REMAINDER)
    args=ap.parse_args()
    cmd=list(args.command)
    if cmd and cmd[0]=="--":cmd=cmd[1:]
    if not cmd:
        raise SystemExit("missing command after --")
    lock_before=check_evidence_lock()
    if lock_before:
        print(json.dumps({"ok":False,"step":args.name,"evidence_lock_before":lock_before},ensure_ascii=False,indent=2))
        return 6
    before=snapshot()
    started=datetime.now(timezone.utc).isoformat()
    proc=subprocess.run(cmd,cwd=ROOT)
    after=snapshot()
    lock_after=check_evidence_lock()
    same=before==after
    allowed_rc=assert_allowed(git_worktree_paths(),label=f"step:{args.name}:worktree")
    record={
        "workflow_run_id":os.getenv("GITHUB_RUN_ID") or "local",
        "workflow_run_attempt":os.getenv("GITHUB_RUN_ATTEMPT") or "local",
        "step":args.name,
        "started_at":started,
        "completed_at":datetime.now(timezone.utc).isoformat(),
        "command":cmd,
        "returncode":proc.returncode,
        "production_boundary_unchanged":same,
        "evidence_lock_unchanged":not lock_after,
        "research_only_worktree":allowed_rc==0,
        "before_hash":snapshot_digest(before),
        "after_hash":snapshot_digest(after),
        "protected_file_count":len((before or {}).get("files") or {}),
    }
    prior=load(AUDIT,{"version":"6.15.8a","records":[]})
    prior["generated_at"]=record["completed_at"]
    # One-time compaction of legacy audit rows: preserve invariant evidence as hashes,
    # not repeated multi-megabyte production snapshots.
    for old_record in prior.get("records",[]):
        if "before" in old_record and "before_hash" not in old_record:
            old_record["before_hash"]=snapshot_digest(old_record.get("before"))
        if "after" in old_record and "after_hash" not in old_record:
            old_record["after_hash"]=snapshot_digest(old_record.get("after"))
        old_record.pop("before",None)
        old_record.pop("after",None)
    prior.setdefault("records",[]).append(record)
    AUDIT.parent.mkdir(parents=True,exist_ok=True)
    AUDIT.write_text(json.dumps(prior,ensure_ascii=False,indent=2),encoding="utf-8")
    if proc.returncode!=0:
        return proc.returncode
    if lock_after:
        print(json.dumps({"ok":False,"step":args.name,"evidence_lock_after":lock_after},ensure_ascii=False,indent=2))
        return 6
    if not same:
        print(json.dumps({"ok":False,"step":args.name,"reason":"production_boundary_changed"},ensure_ascii=False,indent=2))
        return 4
    if allowed_rc!=0:
        return allowed_rc
    print(json.dumps({"ok":True,"step":args.name,"production_boundary_unchanged":True},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
