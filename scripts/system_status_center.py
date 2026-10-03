#!/usr/bin/env python3
"""Build a public, read-only status snapshot for MyAlpha autonomous pipelines."""
from __future__ import annotations

import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"system_status.json"

ARTIFACTS={
    "market_dashboard": ROOT/"docs"/"data.json",
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
    "breadth_intelligence": ROOT/"docs"/"research"/"breadth_intelligence.json",
    "breadth_intelligence_history": ROOT/"docs"/"research"/"breadth_intelligence_history.json",
    "regime_combination_memory": ROOT/"docs"/"research"/"regime_combination_memory.json",
    "regime_combination_history": ROOT/"docs"/"research"/"regime_combination_history.json",
}

WATCH_WORKFLOWS={
    "quant-dashboard":["Daily Dashboard Update","Autonomous QA & Security","Source Intelligence Validation","Trend Pulse 5Y Backtest","pages build and deployment"],
    "wxc-bot":["research-close","tg-bot"],
}

# Maximum expected age before an artifact is excluded from decision/research inputs.
# Thresholds intentionally allow weekends/holidays while preventing silently stale data
# from being presented as current evidence.
FRESHNESS_HOURS={
    "market_dashboard": 72,
    "learning_engine": 96,
    "autonomous_agent": 96,
    "source_intelligence": 120,
    "source_outcomes": 168,
    "evidence_attribution": 168,
    "method_memory": 168,
    "research_planner": 96,
    "research_execution": 96,
    "official_evidence": 168,
    "event_evidence": 96,
    "event_window_attribution": 168,
    "self_improvement": 168,
    "learning_evaluation": 96,
    "module_intelligence": 336,
    "cross_asset_divergence": 96,
    "cross_asset_divergence_history": 336,
    "breadth_intelligence": 96,
    "breadth_intelligence_history": 336,
    "regime_combination_memory": 96,
    "regime_combination_history": 336,
}
CRITICAL_DECISION_ARTIFACTS={
    "market_dashboard","learning_engine","autonomous_agent",
    "cross_asset_divergence","breadth_intelligence","regime_combination_memory",
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

def github_runs(repo:str,names=None,max_pages=5):
    """Fetch enough Actions pages to resolve all watched workflow names.

    Busy repositories can exceed 100 runs quickly because Pages/QA workflows
    create many entries. Stop as soon as every requested workflow has been seen.
    """
    wanted=set(names or [])
    rows=[]
    token=os.getenv("GITHUB_TOKEN")
    try:
        for page in range(1,max_pages+1):
            url=f"https://api.github.com/repos/simonzixin8166-wq/{repo}/actions/runs?per_page=100&page={page}"
            req=urllib.request.Request(url,headers={"User-Agent":"MyAlpha-Status-Center","Accept":"application/vnd.github+json"})
            if token:req.add_header("Authorization",f"Bearer {token}")
            with urllib.request.urlopen(req,timeout=12) as r:
                batch=json.loads(r.read().decode("utf-8")).get("workflow_runs",[])
            rows.extend(batch)
            if wanted and wanted.issubset({x.get("name") for x in rows}):
                break
            if len(batch)<100:
                break
        return rows
    except Exception as exc:
        rows.append({"_error":str(exc)[:180]})
        return rows

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

def parse_iso(value):
    if not value:return None
    try:
        text=str(value).replace("Z","+00:00")
        dt=datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def artifact_health(name,path,now=None):
    now=now or datetime.now(timezone.utc)
    updated=iso_from_file(path)
    dt=parse_iso(updated)
    max_age=FRESHNESS_HOURS.get(name,168)
    age_hours=None if dt is None else round(max(0.0,(now-dt.astimezone(timezone.utc)).total_seconds()/3600),1)
    available=path.exists()
    if not available:
        freshness="missing"
    elif age_hours is None:
        freshness="unknown"
    elif age_hours <= max_age:
        freshness="fresh"
    elif age_hours <= max_age*2:
        freshness="stale"
    else:
        freshness="expired"
    decision_eligible=available and freshness=="fresh"
    return {
        "updated_at":updated,
        "available":available,
        "age_hours":age_hours,
        "max_age_hours":max_age,
        "freshness":freshness,
        "decision_eligible":decision_eligible,
        "participation":"eligible" if decision_eligible else "excluded",
    }

def build(fetch_runs=True):
    repos={}
    for repo,names in WATCH_WORKFLOWS.items():
        rows=latest_by_name(github_runs(repo,names) if fetch_runs else [],names)
        for v in rows.values():v["health"]=health(v.get("conclusion"),v.get("status"))
        repos[repo]=rows
    now=datetime.now(timezone.utc)
    artifacts={k:artifact_health(k,v,now) for k,v in ARTIFACTS.items()}
    overall="ok"
    critical=[
        repos["quant-dashboard"].get("Daily Dashboard Update",{}).get("health"),
        repos["wxc-bot"].get("research-close",{}).get("health"),
    ]
    artifact_failures=[
        name for name in CRITICAL_DECISION_ARTIFACTS
        if not artifacts.get(name,{}).get("decision_eligible")
    ]
    if "bad" in critical:overall="attention"
    elif "running" in critical:overall="running"
    elif any(x in {"unknown",None} for x in critical):overall="attention"
    elif artifact_failures:overall="attention"
    result={
        "version":4,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "overall":overall,
        "workflows":repos,
        "artifacts":artifacts,
        "decision_data_contract":{
            "critical_artifacts":sorted(CRITICAL_DECISION_ARTIFACTS),
            "excluded_artifacts":artifact_failures,
            "rule":"只有 freshness=fresh 且 decision_eligible=true 的关键产物才允许进入当前研究/决策摘要；缓存或过期数据只能作为历史上下文。",
        },
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
