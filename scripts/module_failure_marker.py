#!/usr/bin/env python3
"""Write a public, sanitized module-failure marker without exposing secrets."""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"module_failures.json"

def load():
    try:return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:return {"version":1,"modules":{}}

def main():
    if len(sys.argv)<2:
        raise SystemExit("module name required")
    module=str(sys.argv[1]).strip()
    data=load()
    data.setdefault("version",1);data.setdefault("modules",{})
    now=datetime.now(timezone.utc).isoformat()
    data["generated_at"]=now
    data["modules"][module]={
        "status":"failed",
        "failed_at":now,
        "workflow":os.getenv("GITHUB_WORKFLOW","unknown"),
        "run_id":os.getenv("GITHUB_RUN_ID","unknown"),
        "commit_sha":os.getenv("GITHUB_SHA","unknown"),
        "note":"Module failed in isolated mode; website update continued. Inspect GitHub Actions logs for details.",
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"module":module,"status":"failed","failed_at":now},ensure_ascii=False))

if __name__=="__main__":
    main()
