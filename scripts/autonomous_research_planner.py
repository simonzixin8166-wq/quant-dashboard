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
 "modules":ROOT/"docs/research/module_intelligence.json",
 "cross_asset":ROOT/"docs/research/cross_asset_divergence.json",
 "breadth_intelligence":ROOT/"docs/research/breadth_intelligence.json",
 "regime_memory":ROOT/"docs/research/regime_combination_memory.json",
 "data":ROOT/"docs/data.json",
 "controlled_policy":ROOT/"docs/research/controlled_learning_policy.json",
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

def build(agent,learning,evidence,method,source,previous,modules=None,cross_asset=None,breadth_intelligence=None,regime_memory=None,data=None,controlled_policy=None):
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

    cross_asset=cross_asset or {}
    if cross_asset.get("level") in {"medium","high"}:
        priority=86 if cross_asset.get("level")=="high" else 76
        t=task("cross_asset_divergence","US_MARKET",
          f"美股 · {cross_asset.get('label') or '跨资产背离'}",priority,
          f"指数仍强，但跨资产风险信号已触发 {cross_asset.get('risk_hits',0)} 项。",
          ["10年期与实际利率是否继续上行？","信用利差是否继续走阔？","20/50/200日宽度是否修复？","VIX/MOVE是否开始与债券压力共振？","这种组合历史5/20/60日结果如何？"],
          ["cross_asset_divergence","macro_context","market_breadth","SPY/QQQ","credit"],5)
        t["divergence_level"]=cross_asset.get("level")
        t["risk_hits"]=cross_asset.get("risk_hits")
        tasks.append(t);seen.add(t["task_id"])

    breadth_intelligence=breadth_intelligence or {}
    if breadth_intelligence.get("level") in {"fragile","weakening"}:
        priority=88 if breadth_intelligence.get("level")=="fragile" else 78
        t=task("breadth_intelligence","US_BREADTH",
          f"美股 · {breadth_intelligence.get('label') or '市场宽度异常'}",priority,
          f"市场参与度评分 {breadth_intelligence.get('participation_score','—')}，风险信号 {breadth_intelligence.get('risk_hits',0)} 项。",
          ["20/50日宽度是否连续修复？","RSP是否开始追上SPY？","QQQE是否开始追上QQQ？","长期200日宽度是否重回50%以上？","宽度恶化是否与利率/信用压力共振？"],
          ["breadth_intelligence","market_breadth","SPY/RSP","QQQ/QQQE","cross_asset_divergence"],5)
        t["breadth_level"]=breadth_intelligence.get("level")
        t["participation_score"]=breadth_intelligence.get("participation_score")
        t["combination_key"]=breadth_intelligence.get("combination_key")
        tasks.append(t);seen.add(t["task_id"])

    regime_memory=regime_memory or {}
    if regime_memory.get("level") in {"high","medium"}:
        priority=92 if regime_memory.get("level")=="high" else 82
        t=task("regime_combination","US_REGIME",
          f"美股 · {regime_memory.get('label') or '组合环境研究'}",priority,
          f"当前组合状态 {regime_memory.get('state_id','—')}；需要验证跨资产压力与宽度收窄是否持续共振。",
          ["同类组合状态历史5/20/60日结果如何？","宽度还是利率/信用哪一侧先修复？","VIX是否从低波动补涨确认风险？","什么变化足以让组合状态降级？"],
          ["regime_combination_memory","breadth_intelligence","cross_asset_divergence","SPY","VIX"],5)
        t["state_id"]=regime_memory.get("state_id")
        t["regime_level"]=regime_memory.get("level")
        tasks.append(t);seen.add(t["task_id"])

    data=data or {}
    rebound=data.get("leverage_rebound") or {}
    if rebound.get("available") and rebound.get("status") in {"watch","candidate","risk"}:
        priority=float(rebound.get("priority") or (90 if rebound.get("status")=="risk" else 82))
        t=task("leverage_rebound","QQQ",
          f"QQQ · {rebound.get('label') or 'TQQQ vs LEAPS 回调情境'}",priority,
          rebound.get("prompt") or "QQQ进入回调研究区，需要比较TQQQ与QQQ LEAPS的风险收益结构。",
          ["当前更接近V型修复、震荡筑底还是深熊延续？","TQQQ现有X2规则是否允许恢复敞口？","QQQ LEAPS的IV/Theta/流动性是否合理？","市场宽度是否确认修复？","5/20/60日后哪种情境判断更接近事实？"],
          ["leverage_rebound","TQQQ_X2","LEAPS_Radar","market_breadth","VIX","source_method_lionhill"],5)
        t["rebound_status"]=rebound.get("status")
        t["qqq_drawdown"]=rebound.get("drawdown252")
        t["source_method"]=rebound.get("source_method")
        tasks.append(t);seen.add(t["task_id"])

    controlled_policy=controlled_policy or {}
    replay_ev=controlled_policy.get("replay_evidence") or {}
    forward_ev=controlled_policy.get("forward_evidence") or {}
    bonus_map=controlled_policy.get("playbook_validation_priority_bonus") or {}
    for pid in ("CP-01","CP-02","CP-03"):
        r=replay_ev.get(pid) or {}
        f=forward_ev.get(pid) or {}
        bonus=float(bonus_map.get(pid) or 0)
        if not r and not f:continue
        t=task("playbook_validation",pid,f"{pid} · Replay/Forward 证据验证",60+bonus,
          f"Replay有效样本 {r.get('effective_n',0)}；Forward 5日成熟样本 {f.get('mature5',0)}。历史回放与真实前瞻必须继续分开验证。",
          ["Replay 与 Forward 的方向一致性是否一致？","失败样本集中在哪些市场环境？","有效样本是否存在聚类或样本不足？","下一批 Forward 样本成熟后证据状态是否变化？"],
          ["walk_forward_replay","playbook_outcome_shadow","playbook_status","decision_journal"],20)
        t["replay_evidence_state"]=r.get("state")
        t["forward_evidence_state"]=f.get("state")
        t["controlled_priority_bonus"]=bonus
        if t["task_id"] not in seen:tasks.append(t);seen.add(t["task_id"])

    modules=modules or {}
    audit=modules.get("audit") or {}
    if not audit.get("coverage_ok",True):
        t=task("architecture_gap","module_registry","网站模块关系审计异常",90,
          "存在未登记或已失效的一级模块，可能形成数据或学习孤岛。",
          ["哪些页面未声明存在目的？","哪些模块没有输入或输出？","是否有私有数据越界？","需要合并、淘汰还是接入Agent Loop？"],
          ["module_intelligence","system_status","autonomous_qa"],1)
        tasks.append(t);seen.add(t["task_id"])
    for m in modules.get("modules") or []:
        mode=m.get("learning")
        if mode in {"candidate","shadow_only","private_shadow"}:
            t=task("module_learning_review",m.get("id"),f"{m.get('name')} · 学习闭环审核",58,
              f"该模块当前学习模式为 {mode}，需要持续判断是否具备可靠结果标签与升级条件。",
              ["该模块的输出是否可被后续结果验证？","是否存在重复证据或数据泄漏？","哪些结果可以进入Shadow学习？","什么时候应保持静态而不是学习？"],
              ["module_intelligence","decision_journal","failure_attribution","self_improvement"],30)
            if t["task_id"] not in seen:tasks.append(t);seen.add(t["task_id"])
    policy_delta=controlled_policy.get("task_kind_priority_delta") or {}
    for t in tasks:
        base=float(t.get("priority") or 0)
        delta=float(policy_delta.get(t.get("kind")) or 0)
        delta=max(-5.0,min(5.0,delta))
        t["base_priority"]=round(base,1)
        t["controlled_learning_delta"]=round(delta,2)
        t["priority"]=max(0,min(100,round(base+delta,1)))

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
      "version":"6.8.2","generated_at":now,"mode":"autonomous_research_planner",
      "queue":tasks[:30],
      "today":[x for x in tasks if x["priority"]>=70][:10],
      "counts":{"open":len(tasks),"high_priority":sum(x["priority"]>=70 for x in tasks),"persistent":sum(x["run_count"]>1 for x in tasks)},
      "planner_policy":{
        "objective":"优先研究可能改变 Thesis、风险暴露或方法可信度的问题。",
        "required_output":["supporting_evidence","counter_evidence","unknowns","next_validation"],
        "controlled_learning":"bounded research-only priority/evidence adjustments; max +/-5 points; no production-rule mutation",
        "forbidden":["automatic_order","silent_production_rule_change","single-source conclusion"]
      }
    }

def main():
    d={k:load(v) for k,v in PATHS.items()}
    out=build(d["agent"],d["learning"],d["evidence"],d["method"],d["source"],d["previous"],d["modules"],d["cross_asset"],d["breadth_intelligence"],d["regime_memory"],d["data"],d["controlled_policy"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
