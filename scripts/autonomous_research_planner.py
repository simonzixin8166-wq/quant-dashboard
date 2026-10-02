#!/usr/bin/env python3
"""MyAlpha V6 Autonomous Research Planner.

Builds a persistent research queue from current market situations, agent alerts,
external-source validation, failure attribution and method memory. It does not
place trades or modify production rules.
"""
from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATHS={
 "agent":ROOT/"docs/research/autonomous_agent.json",
 "learning":ROOT/"docs/research/learning_engine.json",
 "evidence":ROOT/"docs/research/evidence_attribution.json",
 "method":ROOT/"docs/research/method_memory.json",
 "source":ROOT/"docs/data/source_intelligence.json",
 "previous":ROOT/"docs/research/research_planner.json",
}
OUT=ROOT/"docs/research/research_planner.json"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def uid(kind,key):
    return hashlib.sha1(f"{kind}|{key}".encode()).hexdigest()[:14]

def task(kind,key,title,priority,why,questions,sources,expires=2):
    return {
      "task_id":uid(kind,key),"kind":kind,"key":key,"title":title,
      "priority":max(0,min(100,round(float(priority),1))),
      "why_now":why,"questions":questions,"evidence_sources":sources,
      "status":"open","review_window_days":expires,
      "guardrail":"研究任务不是交易指令；结论必须同时记录支持证据、反证与未知项。"
    }

def build(agent,learning,evidence,method,source,previous):
    tasks=[]
    seen=set()
    for row in agent.get("watchlist_attention") or []:
        if row.get("level") not in {"review","action"}:continue
        sym=row.get("symbol")
        floor=88 if row.get("level")=="action" else 72
        p=max(float(row.get("research_priority") or 0),floor)
        t=task("market_anomaly",sym,f"{sym} · 异动/趋势专项研究",p,
          "；".join(row.get("reasons") or ["市场状态变化"]),
          ["这次变化由公司事件、行业共振还是市场因素驱动？","支持原 Thesis 的证据是什么？","最强反证是什么？","明日需要验证什么？"],
          ["market_data","trend_pulse","SEC/IR","company_news","industry_peers"])
        tasks.append(t);seen.add(t["task_id"])
    failure_groups={}
    for row in (evidence.get("failure_attribution") or {}).get("external_outcome_reviews") or []:
        key=str(row.get("symbol") or "UNKNOWN")
        failure_groups.setdefault(key,[]).append(row)
    for sym,rows in failure_groups.items():
        t=task("failure_review",sym,f"{sym} · 失败归因复盘（{len(rows)}样本）",68,
          f"该标的累计 {len(rows)} 个外部研究失效/反例样本，需要归纳共同失败机制。",
          ["这些失败是否共享同一市场环境？","主要来自趋势、事件、估值、宏观还是数据问题？","是否存在重复的反证线索？","应调整研究权重还是仅记录反例？"],
          ["source_outcomes","evidence_attribution","method_memory","market_history"],5)
        t["sample_count"]=len(rows)
        t["example_event_ids"]=[str(x.get("event_id") or "") for x in rows[:5]]
        if t["task_id"] not in seen:tasks.append(t);seen.add(t["task_id"])
    for m in method.get("methods") or []:
        direct=m.get("direct_validated_events") or 0
        context=m.get("context_validated_events") or 0
        if context>=8 and direct<3:
            t=task("method_evidence_gap",m.get("method"),f"{m.get('method')} · 补足直接证据",62,
              f"已有 {context} 个上下文验证，但只有 {direct} 个可直接归因样本。",
              ["哪些事件可以直接归因到该方法？","需要补充哪些触发条件字段？","哪些 Context 样本应保持排除？"],
              ["method_memory","source_intelligence","source_outcomes"],14)
            if t["task_id"] not in seen:tasks.append(t);seen.add(t["task_id"])
    for d in agent.get("discovery_queue") or []:
        sym=d.get("symbol")
        t=task("discovery",sym,f"{sym} · 新机会核验",70 if d.get("event_strength")=="high" else 60,
          d.get("next_step") or "异常事件进入自主研究队列。",
          ["是否存在官方公告或可靠新闻？","是否有行业联动？","异常是否持续？","有什么反证？"],
          ["SEC/IR","reliable_news","market_data","industry_peers"],2)
        if t["task_id"] not in seen:tasks.append(t);seen.add(t["task_id"])

    old={x.get("task_id"):x for x in previous.get("queue") or []}
    for t in tasks:
        if t["task_id"] in old:
            t["first_seen_at"]=old[t["task_id"]].get("first_seen_at")
            t["run_count"]=(old[t["task_id"]].get("run_count") or 0)+1
        else:
            t["first_seen_at"]=datetime.now(timezone.utc).isoformat()
            t["run_count"]=1
    tasks.sort(key=lambda x:(x["priority"],x["run_count"]),reverse=True)
    now=datetime.now(timezone.utc).isoformat()
    return {
      "version":"6.0.1","generated_at":now,"mode":"autonomous_research_planner",
      "queue":tasks[:30],
      "today":[x for x in tasks if x["priority"]>=70][:10],
      "counts":{"open":len(tasks),"high_priority":sum(x["priority"]>=70 for x in tasks),"persistent":sum(x["run_count"]>1 for x in tasks)},
      "planner_policy":{
        "objective":"优先研究可能改变 Thesis、风险暴露或方法可信度的问题。",
        "required_output":["supporting_evidence","counter_evidence","unknowns","next_validation"],
        "forbidden":["automatic_order","silent_production_rule_change","single-source conclusion"]
      }
    }

def main():
    d={k:load(v) for k,v in PATHS.items()}
    out=build(d["agent"],d["learning"],d["evidence"],d["method"],d["source"],d["previous"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
