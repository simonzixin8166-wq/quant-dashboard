#!/usr/bin/env python3
"""Run one V6.15 research step under a per-step production hash invariant."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from research_boundary_guard import snapshot, assert_allowed, git_worktree_paths

AUDIT=ROOT/"research"/"audit"/"step_boundary_log.json"

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
    before=snapshot()
    started=datetime.now(timezone.utc).isoformat()
    proc=subprocess.run(cmd,cwd=ROOT)
    after=snapshot()
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
        "research_only_worktree":allowed_rc==0,
        "before":before,
        "after":after,
    }
    prior=load(AUDIT,{"version":"6.15.8a","records":[]})
    prior["generated_at"]=record["completed_at"]
    prior.setdefault("records",[]).append(record)
    prior["records"]=prior["records"][-200:]
    AUDIT.parent.mkdir(parents=True,exist_ok=True)
    AUDIT.write_text(json.dumps(prior,ensure_ascii=False,indent=2),encoding="utf-8")
    if proc.returncode!=0:
        return proc.returncode
    if not same:
        print(json.dumps({"ok":False,"step":args.name,"reason":"production_boundary_changed"},ensure_ascii=False,indent=2))
        return 4
    if allowed_rc!=0:
        return allowed_rc
    print(json.dumps({"ok":True,"step":args.name,"production_boundary_unchanged":True},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
