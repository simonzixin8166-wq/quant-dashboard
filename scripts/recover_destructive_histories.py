#!/usr/bin/env python3
"""Recover records previously lost to destructive history caps from Git history.

Targets:
- research/audit/step_boundary_log.json (legacy cap 80)
- docs/data.json -> opportunity_history (legacy cap 240)

This is one-time/repeatable recovery. Current fields win; historical versions
only restore missing immutable records.
"""
from __future__ import annotations
import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BOUNDARY=ROOT/"research"/"audit"/"step_boundary_log.json"
DATA=ROOT/"docs"/"data.json"
REPORT=ROOT/"research"/"audit"/"destructive_history_recovery_report.json"

def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL)

def load_text(text):
    try:return json.loads(text)
    except Exception:return {}

def commits(path):
    raw=git("log","--format=%H","--",str(path.relative_to(ROOT)))
    return [x for x in raw.splitlines() if x.strip()]

def version(commit,path):
    try:return load_text(git("show",f"{commit}:{path.relative_to(ROOT)}"))
    except Exception:return {}

def boundary_key(r):
    raw="|".join(str(r.get(k) or "") for k in ("workflow_run_id","workflow_run_attempt","step","started_at","completed_at"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def opportunity_key(r):
    raw="|".join(str(r.get(k) or "") for k in ("date","kind","symbol","strategy","state","action","trigger"))
    if not raw.replace("|",""):
        raw=json.dumps(r,sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def recover():
    current_boundary=load_text(BOUNDARY.read_text(encoding="utf-8")) if BOUNDARY.exists() else {"version":1,"records":[]}
    bmap={boundary_key(r):dict(r) for r in (current_boundary.get("records") or [])}
    before_b=len(bmap)
    bcommits=commits(BOUNDARY)
    for sha in bcommits:
        doc=version(sha,BOUNDARY)
        for r in doc.get("records") or []:
            bmap.setdefault(boundary_key(r),dict(r))
    brows=sorted(bmap.values(),key=lambda r:(str(r.get("started_at") or ""),str(r.get("workflow_run_id") or ""),str(r.get("step") or "")))
    current_boundary["records"]=brows
    current_boundary["retention_policy"]="append_only_no_record_count_cap"
    current_boundary["historical_recovery"]={
      "completed_at":datetime.now(timezone.utc).isoformat(),
      "git_commits_scanned":len(bcommits),
      "before":before_b,"after":len(brows),"recovered":len(brows)-before_b,
    }
    BOUNDARY.parent.mkdir(parents=True,exist_ok=True)
    BOUNDARY.write_text(json.dumps(current_boundary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    current_data=load_text(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    omap={opportunity_key(r):dict(r) for r in (current_data.get("opportunity_history") or [])}
    before_o=len(omap)
    dcommits=commits(DATA)
    max_historical_o=before_o
    versions_with_o=0
    for sha in dcommits:
        doc=version(sha,DATA)
        rows=doc.get("opportunity_history") or []
        if rows:
            versions_with_o+=1
            max_historical_o=max(max_historical_o,len(rows))
        for r in rows:
            omap.setdefault(opportunity_key(r),dict(r))
    orows=sorted(omap.values(),key=lambda r:(str(r.get("date") or ""),str(r.get("kind") or ""),str(r.get("symbol") or "")),reverse=True)
    current_data["opportunity_history"]=orows
    if orows:
        current_data["opportunity_history_retention_policy"]="append_only_no_record_count_cap"
        DATA.write_text(json.dumps(current_data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    report={
      "version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "boundary_log":{
        "git_commits_scanned":len(bcommits),"before":before_b,"after":len(brows),"recovered":len(brows)-before_b,
      },
      "opportunity_history":{
        "git_commits_scanned":len(dcommits),"versions_with_records":versions_with_o,
        "max_records_in_any_historical_version":max_historical_o,
        "before":before_o,"after":len(orows),"recovered":len(orows)-before_o,
      },
      "guardrail":"Recovered audit/research history has no authority to mutate Production trading rules.",
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":recover()
