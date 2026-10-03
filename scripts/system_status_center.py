#!/usr/bin/env python3
"""Build a public, read-only status snapshot for MyAlpha autonomous pipelines."""
from __future__ import annotations

import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"system_status.json"

ARTIFACTS={
    "market_dashboard": ROOT/"docs"/"data"/"dashboard.json",
    "learning_engine": ROOT/"docs"/"research"/"learning_engine.json",
    "autonomous_agent": ROOT/"docs"/"research"/"autonomous_agent.json",
    "source_intelligence": ROOT/"docs"/"data"/"source_intelligence.json",
    "source_outcomes": ROOT/"docs"/"research"/"source_outcome_validation.json",
    "evidence_attribution": ROOT/"docs"/"research"/"evidence_attribution.json",
    "method_memory": ROOT/"docs"/"research"/"method_memory.json",
    "research_planner": ROOT/"docs"/"research"/"research_planner.json",
    "research_execution": ROOT/"docs"/"research"/"research_execution.json",
    "official_evidence": ROOT/"docs"/"research"/"official_evidence.json",
    "event_evidence": ROOT/"docs"/"research"/"event_evidence.json",
    "event_window_attribution": ROOT/"docs"/"research"/"event_window_attribution.json",
    "self_improvement": ROOT/"docs"/"research"/"self_improvement.json",
    "module_intelligence": ROOT/"docs"/"research"/"module_intelligence.json",
    "cross_asset_divergence": ROOT/"docs"/"research"/"cross_asset_divergence.json",
    "cross_asset_divergence_history": ROOT/"docs"/"research"/"cross_asset_divergence_history.json",
}

WATCH_WORKFLOWS={
    "quant-dashboard":["Daily Dashboard Update","Source Intelligence Validation","Trend Pulse 5Y Backtest","pages build and deployment"],
    "wxc-bot":["research-close","tg-bot"],
}

def load(path:Path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def iso_from_file(path:Path):
    if not path.exists():return None
    data=load(path)
    for k in ("generated_at","updated_at","curation_updated_at","as_of","generatedAt"):
        if data.get(k):return str(data[k])
    return datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()

def github_runs(repo:str):
    url=f"https://api.github.com/repos/simonzixin8166-wq/{repo}/actions/runs?per_page=100"
    req=urllib.request.Request(url,headers={"User-Agent":"MyAlpha-Status-Center","Accept":"application/vnd.github+json"})
    token=os.getenv("GITHUB_TOKEN")
    if token:req.add_header("Authorization",f"Bearer {token}")
    try:
        with urllib.request.urlopen(req,timeout=12) as r:
            return json.loads(r.read().decode("utf-8")).get("workflow_runs",[])
    except Exception as exc:
        return [{"_error":str(exc)[:180]}]

def latest_by_name(runs,names):
    out={}
    err=next((x.get("_error") for x in runs if x.get("_error")),None)
    for name in names:
        row=next((x for x in runs if x.get("name")==name),None)
        if row:
            out[name]={
                "status":row.get("status"),"conclusion":row.get("conclusion"),
                "event":row.get("event"),"created_at":row.get("created_at"),
                "updated_at":row.get("updated_at"),"head_sha":row.get("head_sha"),
            }
        else:
            out[name]={"status":"unknown","conclusion":None,"error":err or "no recent run found"}
    return out

def health(conclusion,status):
    if status in {"queued","in_progress","waiting","pending"}:return "running"
    if conclusion=="success":return "ok"
    if conclusion in {"failure","startup_failure","timed_out","cancelled"}:return "bad"
    if conclusion=="skipped":return "neutral"
    return "unknown"

def build(fetch_runs=True):
    repos={}
    for repo,names in WATCH_WORKFLOWS.items():
        rows=latest_by_name(github_runs(repo) if fetch_runs else [],names)
        for v in rows.values():v["health"]=health(v.get("conclusion"),v.get("status"))
        repos[repo]=rows
    artifacts={k:{"updated_at":iso_from_file(v),"available":v.exists()} for k,v in ARTIFACTS.items()}
    overall="ok"
    critical=[
        repos["quant-dashboard"].get("Daily Dashboard Update",{}).get("health"),
        repos["wxc-bot"].get("research-close",{}).get("health"),
    ]
    if "bad" in critical:overall="attention"
    elif "running" in critical:overall="running"
    elif any(x in {"unknown",None} for x in critical):overall="attention"
    result={
        "version":2,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "overall":overall,
        "workflows":repos,
        "artifacts":artifacts,
        "principle":"状态中心只报告自动化健康度与数据新鲜度；不会修改交易规则。",
    }
    return result

def main():
    result=build(True)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"overall":result["overall"],"generated_at":result["generated_at"]},ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
