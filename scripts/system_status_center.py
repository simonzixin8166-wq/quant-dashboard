#!/usr/bin/env python3
"""Build a public, read-only status snapshot for MyAlpha autonomous pipelines."""
from __future__ import annotations

import json, os, urllib.request, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import trading_calendar
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
    "playbook_status": ROOT/"docs"/"research"/"playbook_status.json",
    "ledger_anchor": ROOT/"docs"/"research"/"ledger_anchor.json",
    "range_intelligence": ROOT/"docs"/"research"/"range_intelligence.json",
    "module_failures": ROOT/"docs"/"research"/"module_failures.json",
    "playbook_outcome_shadow": ROOT/"docs"/"research"/"playbook_outcome_shadow.json",
    "walk_forward_replay": ROOT/"docs"/"research"/"walk_forward_replay.json",
    "controlled_learning_policy": ROOT/"docs"/"research"/"controlled_learning_policy.json",
    "forward_learning_feedback": ROOT/"docs"/"research"/"forward_learning_feedback.json",
    "challenger_experiments": ROOT/"docs"/"research"/"challenger_experiments.json",
    "source_reading_memory": ROOT/"docs"/"research"/"source_reading_memory.json",
    "source_rule_lifecycle": ROOT/"docs"/"research"/"source_rule_lifecycle.json",
    "support_volatility_intelligence": ROOT/"docs"/"research"/"support_volatility_intelligence.json",
    "options_opportunity_context": ROOT/"docs"/"research"/"options_opportunity_context.json",
}

WATCH_WORKFLOWS={
    "quant-dashboard":["Daily Dashboard Update","Autonomous QA & Security","Source Intelligence Validation","Trend Pulse 5Y Backtest","pages build and deployment","Playbook Independent Watchdog"],
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
    "playbook_status": 96,
    "ledger_anchor": 96,
    "range_intelligence": 96,
    "module_failures": 720,
    "playbook_outcome_shadow": 96,
    "walk_forward_replay": 168,
    "controlled_learning_policy": 168,
    "forward_learning_feedback": 168,
    "challenger_experiments": 168,
    "source_reading_memory": 168,
    "source_rule_lifecycle": 168,
    "support_volatility_intelligence": 96,
    "options_opportunity_context": 96,
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

def github_runs(repo:str,names=None,max_pages=20):
    """Fetch enough Actions pages to resolve all watched workflow names.

    Busy repositories can exceed 500 runs quickly because Pages/QA workflows
    create many entries. Search a deeper bounded window for low-frequency
    workflows, but stop as soon as every requested workflow has been seen.
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
    if conclusion in {"failure","startup_failure","timed_out"}:return "bad"
    if conclusion in {"cancelled","skipped"}:return "neutral"
    return "unknown"

def parse_iso(value):
    if not value:return None
    try:
        text=str(value).replace("Z","+00:00")
        dt=datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_nyse_session_day(d):
    return trading_calendar.is_session(d)

def expected_completed_us_session(now=None):
    return trading_calendar.expected_latest_completed_session(now).isoformat()

def market_business_freshness(path,now=None):
    data=load(path)
    market_as_of=str(data.get("spy_date") or ((data.get("index") or {}).get("SPY") or {}).get("date") or "")
    expected=expected_completed_us_session(now)
    if not market_as_of:
        status="unknown"
    elif market_as_of==expected:
        status="fresh"
    elif market_as_of<expected:
        status="stale"
    else:
        status="future"
    return {"market_as_of":market_as_of or None,"expected_market_date":expected,"business_freshness":status}

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
    freshness_eligible=available and freshness=="fresh"
    research_only=name in {"range_intelligence","playbook_outcome_shadow","walk_forward_replay","controlled_learning_policy","forward_learning_feedback","challenger_experiments","source_reading_memory","source_rule_lifecycle","support_volatility_intelligence","options_opportunity_context"}
    business={}
    if name=="market_dashboard" and available:
        business=market_business_freshness(path,now)
        freshness_eligible=freshness_eligible and business.get("business_freshness")=="fresh"
    decision_eligible=freshness_eligible and not research_only
    out={
        "updated_at":updated,
        "available":available,
        "age_hours":age_hours,
        "max_age_hours":max_age,
        "freshness":freshness,
        "decision_eligible":decision_eligible,
        "participation":"research_only" if research_only and freshness_eligible else ("eligible" if decision_eligible else "excluded"),
    }
    if business:out.update(business)
    return out


def build_resource_guard(repos, artifacts):
    """Operational free-first guardrail.

    This is intentionally a pressure/behavior guard, not a billing meter.
    Provider billing/quota APIs are not required, so unknown commercial usage
    is never fabricated. The guard only decides when MyAlpha should prefer
    cache/event-driven/low-frequency behavior.
    """
    q_runs=list((repos.get("quant-dashboard") or {}).values())
    w_runs=list((repos.get("wxc-bot") or {}).values())
    running=sum(1 for x in q_runs+w_runs if x.get("status") in {"queued","in_progress","waiting","pending"})
    unhealthy=sum(1 for x in q_runs+w_runs if x.get("health")=="bad")
    stale=sum(1 for x in artifacts.values() if x.get("freshness") in {"stale","expired","missing"})
    pressure="normal"
    reasons=[]
    if unhealthy>=2 or stale>=6:
        pressure="conserve";reasons.append("multiple workflow/artifact problems: avoid expanding external requests")
    elif running>=4 or unhealthy or stale>=3:
        pressure="watch";reasons.append("elevated automation/data pressure")
    else:
        reasons.append("current automation/data pressure is low")
    return {
        "mode":pressure,
        "billing_meter":False,
        "free_first":True,
        "signals":{"running_workflows":running,"unhealthy_workflows":unhealthy,"stale_or_missing_artifacts":stale},
        "policies":{
            "market_quotes":"cache first; regular watchlist 10-15m; open options 15m",
            "official_evidence":"event-driven/incremental; no full-market crawl",
            "youtube_historical":"weekly/manual retry with backoff",
            "forward_sources":"new-item incremental only",
            "thesis_refresh":"only when evidence hash changes or user adds a symbol",
            "degrade_order":["historical retries","noncritical news enrichment","broad opportunity enrichment","core risk monitoring last"],
        },
        "reason":"; ".join(reasons),
    }

def build(fetch_runs=True):
    repos={}
    for repo,names in WATCH_WORKFLOWS.items():
        rows=latest_by_name(github_runs(repo,names) if fetch_runs else [],names)
        for v in rows.values():v["health"]=health(v.get("conclusion"),v.get("status"))
        repos[repo]=rows
    now=datetime.now(timezone.utc)
    artifacts={k:artifact_health(k,v,now) for k,v in ARTIFACTS.items()}
    market_gate=artifacts.get("market_dashboard",{}).get("decision_eligible",False)
    if not market_gate:
        for name in CRITICAL_DECISION_ARTIFACTS-{"market_dashboard"}:
            if name in artifacts:
                artifacts[name]["decision_eligible"]=False
                artifacts[name]["participation"]="excluded"
                artifacts[name]["blocked_by"]="market_dashboard_business_freshness"
    overall="ok"
    critical=[
        repos["quant-dashboard"].get("Daily Dashboard Update",{}).get("health"),
        repos["wxc-bot"].get("research-close",{}).get("health"),
    ]
    artifact_failures=[
        name for name in CRITICAL_DECISION_ARTIFACTS
        if not artifacts.get(name,{}).get("decision_eligible")
    ]
    playbook=load(ARTIFACTS["playbook_status"])
    ledger=load(ARTIFACTS["ledger_anchor"])
    failures=load(ARTIFACTS["module_failures"])
    ledger_fault=bool((playbook.get("storage") or {}).get("forward_clock_active") and ledger.get("status")!="ok")
    playbook_generated=parse_iso(playbook.get("generated_at"))
    playbook_failure=parse_iso((((failures.get("modules") or {}).get("playbook_engine") or {}).get("failed_at")))
    unresolved_playbook_failure=bool(playbook_failure and (not playbook_generated or playbook_failure>playbook_generated))
    if "bad" in critical:overall="attention"
    elif "running" in critical:overall="running"
    elif any(x in {"unknown",None} for x in critical):overall="attention"
    elif artifact_failures:overall="attention"
    elif ledger_fault:overall="attention"
    elif unresolved_playbook_failure:overall="attention"
    result={
        "version":4,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "overall":overall,
        "workflows":repos,
        "artifacts":artifacts,
        "range_research":{
            "artifact":artifacts.get("range_intelligence",{}),
            "mode":load(ARTIFACTS["range_intelligence"]).get("mode","unknown"),
            "production_semantics_frozen":load(ARTIFACTS["range_intelligence"]).get("production_semantics_frozen"),
        },
        "playbook_runtime":{
            "mode":playbook.get("mode","unknown"),
            "heartbeat":playbook.get("heartbeat") or {},
            "data_quality":playbook.get("data_quality") or {},
            "kill_switch":playbook.get("kill_switch") or {},
            "storage":playbook.get("storage") or {},
            "ledger_anchor_status":ledger.get("status","unknown"),
            "unresolved_failure":unresolved_playbook_failure,
            "failure_marker":((failures.get("modules") or {}).get("playbook_engine") or {}),
        },
        "resource_guard":build_resource_guard(repos,artifacts),
        "decision_data_contract":{
            "critical_artifacts":sorted(CRITICAL_DECISION_ARTIFACTS),
            "excluded_artifacts":artifact_failures,
            "rule":"关键产物必须同时满足文件 freshness 与业务日期 freshness；market_as_of 必须等于 expected_market_date，才允许进入当前研究/决策摘要。缓存或过期数据只能作为历史上下文。",
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
