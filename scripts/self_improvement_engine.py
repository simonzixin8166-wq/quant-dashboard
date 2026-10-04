#!/usr/bin/env python3
"""MyAlpha V7 Self-Improvement Engine.

Creates candidate research-policy changes from measured evidence, evaluates them
in shadow mode and enforces a promotion gate. It never edits production trading
rules or places orders.
"""
from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/research/evidence_attribution.json"
METHOD=ROOT/"docs/research/method_memory.json"
PLANNER=ROOT/"docs/research/research_planner.json"
MODULES=ROOT/"docs/research/module_intelligence.json"
EXECUTION=ROOT/"docs/research/research_execution.json"
CROSS_HISTORY=ROOT/"docs/research/cross_asset_divergence_history.json"
BREADTH_HISTORY=ROOT/"docs/research/breadth_intelligence_history.json"
REGIME_HISTORY=ROOT/"docs/research/regime_combination_history.json"
MARKET=ROOT/"docs/data.json"
PREV=ROOT/"docs/research/self_improvement.json"
OUT=PREV

def load(p):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {}

def cid(kind,payload):
    return hashlib.sha1((kind+"|"+json.dumps(payload,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()[:14]

def candidate(kind,scope,change,reason,n):
    payload={"scope":scope,"change":change}
    return {"candidate_id":cid(kind,payload),"kind":kind,"scope":scope,"proposed_change":change,
            "reason":reason,"evidence_n":n,"state":"shadow","created_at":datetime.now(timezone.utc).isoformat()}

def _market_day(market, planner):
    day=(market or {}).get("spy_date") or (market or {}).get("updated")
    if day:return str(day)[:10]
    ts=(planner or {}).get("generated_at") or datetime.now(timezone.utc).isoformat()
    return str(ts)[:10]

def build(evidence,method,planner,previous,modules=None,execution=None,cross_history=None,breadth_history=None,regime_history=None,market=None):
    candidates=[]
    market_day=_market_day(market,planner)
    legacy_method=method.get("evidence_role")=="legacy_descriptive_only"
    legacy_external_outcomes=evidence.get("external_outcome_evidence_role")=="legacy_descriptive_only"
    for m in ([] if legacy_method else (method.get("methods") or [])):
        n=m.get("direct_validated_events") or 0
        perf=m.get("performance") or {}
        x20=perf.get("20") or {}
        rate=x20.get("alignment_rate")
        if n>=8 and rate is not None:
            delta=3 if rate>=0.65 else -3 if rate<=0.40 else 0
            if delta:
                candidates.append(candidate("research_weight",m.get("method"),
                  {"priority_weight_delta":delta},
                  f"20日直接样本 alignment_rate={rate:.2f}，样本={n}；仅建议研究排序权重。",n))
    f=(evidence.get("failure_attribution") or {})
    failn=0 if legacy_external_outcomes else len(f.get("external_outcome_reviews") or [])
    if failn>=10:
        candidates.append(candidate("process_guardrail","failure_review",
          {"require_counter_evidence":True,"minimum_counter_items":1},
          f"已有 {failn} 个外部结果复盘候选，增加反证检查作为候选研究流程。",failn))

    modules=modules or {}
    for m in modules.get("modules") or []:
        if m.get("learning")=="candidate":
            candidates.append(candidate("module_learning_design",m.get("id"),
              {"target_mode":"shadow_only","require_outcome_labels":True},
              f"{m.get('name')} 当前仅为 candidate 学习模式；先建立结果标签，再考虑Shadow化。",0))
    execution=execution or {}
    exrows=execution.get("results") or []
    unknown_heavy=sum(1 for x in exrows if len(x.get("unknowns") or [])>=2)
    if unknown_heavy>=4:
        candidates.append(candidate("research_process","evidence_coverage",
          {"require_explicit_unknowns":True,"prioritize_missing_official_evidence":True},
          f"本轮 {unknown_heavy}/{len(exrows)} 个自主研究结果存在两项以上未知信息；建议优先补齐官方证据连接。",len(exrows)))
    cross_history=cross_history or {}
    mature20=[]
    for row in cross_history.get("records") or []:
        if row.get("level") not in {"medium","high"}: continue
        v=((row.get("outcomes") or {}).get("20") or {}).get("return")
        if isinstance(v,(int,float)): mature20.append(v)
    if len(mature20)>=20:
        avg20=sum(mature20)/len(mature20)
        if avg20<=-0.02:
            candidates.append(candidate("research_weight","cross_asset_divergence",
              {"priority_weight_delta":3,"when":"medium_or_high_divergence"},
              f"跨资产背离20日成熟样本 {len(mature20)}，平均SPY收益 {avg20:+.2%}；仅建议提高研究优先级，不改变仓位。",len(mature20)))
    breadth_history=breadth_history or {}
    breadth20=[]
    for row in breadth_history.get("records") or []:
        if row.get("level") not in {"fragile","weakening"}: continue
        v=((row.get("outcomes") or {}).get("20") or {}).get("return")
        if isinstance(v,(int,float)): breadth20.append(v)
    if len(breadth20)>=20:
        avg20=sum(breadth20)/len(breadth20)
        if avg20<=-0.015:
            candidates.append(candidate("research_weight","breadth_intelligence",
              {"priority_weight_delta":2,"when":"fragile_or_weakening_breadth"},
              f"弱宽度20日成熟样本 {len(breadth20)}，平均SPY收益 {avg20:+.2%}；仅建议提高研究优先级，不改变仓位。",len(breadth20)))

    regime_history=regime_history or {}
    regime20=[]
    for row in regime_history.get("records") or []:
        if row.get("level")!="high": continue
        v=((row.get("outcomes") or {}).get("20") or {}).get("return")
        if isinstance(v,(int,float)): regime20.append(v)
    if len(regime20)>=20:
        avg20=sum(regime20)/len(regime20)
        if avg20<=-0.02:
            candidates.append(candidate("research_weight","regime_combination",
              {"priority_weight_delta":3,"when":"high_joint_regime"},
              f"高风险组合环境20日成熟样本 {len(regime20)}，平均SPY收益 {avg20:+.2%}；仅建议提高组合研究优先级。",len(regime20)))

    old={x.get("candidate_id"):x for x in previous.get("candidates") or []}
    promoted=[];shadow=[]
    for c in candidates:
        prior=old.get(c["candidate_id"],{})
        workflow_runs=(prior.get("workflow_runs") or prior.get("shadow_runs") or 0)+1
        prior_days=list(prior.get("shadow_days") or [])
        if not prior_days:
            first=(prior.get("first_seen_at") or c["created_at"])[:10]
            if first: prior_days=[first]
        if market_day and market_day not in prior_days:
            prior_days.append(market_day)
        prior_days=sorted(set(prior_days))
        market_days=len(prior_days)
        c["workflow_runs"]=workflow_runs
        c["shadow_runs"]=market_days
        c["shadow_market_days"]=market_days
        c["shadow_days"]=prior_days
        c["market_day"]=market_day
        c["first_seen_at"]=prior.get("first_seen_at") or c["created_at"]
        # Conservative automatic gate: research-process changes only, >=20 evidence,
        # >=5 distinct market days; repeated workflows on the same market day are not independent evidence.
        eligible=(c["evidence_n"]>=20 and market_days>=5 and c["kind"] in {"research_weight","process_guardrail"})
        c["promotion_eligible"]=eligible
        c["state"]="eligible_for_review" if eligible else "shadow"
        shadow.append(c)
        if eligible: promoted.append(c["candidate_id"])

    return {
      "version":"7.2.1","generated_at":datetime.now(timezone.utc).isoformat(),
      "production_brain":{"mode":"locked","rule":"正式交易阈值与仓位规则不由本引擎自动修改。"},
      "learning_brain":{"planner_version":planner.get("version"),"open_tasks":(planner.get("counts") or {}).get("open",0)},
      "candidate_brain":{"count":len(shadow)},
      "shadow_brain":{"candidates":shadow,"eligible_for_review":promoted},
      "promotion_gate":{
        "automatic_production_promotion":False,
        "minimum_evidence_n":20,"minimum_shadow_market_days":5,"minimum_shadow_runs":5,
        "allowed_scope":["research_priority","research_process"],
        "forbidden_scope":["orders","position_size","core_allocation","hard_exit_thresholds"],
        "decision":"human_review_required"
      },
      "candidates":shadow,
      "guardrails":[
        "候选策略只能在 Shadow 模式积累证据；同一交易日重复 workflow 不重复计为独立 Shadow 样本。",
        "达到门槛仅代表可复核，不自动晋级正式交易规则。",
        "任何涉及仓位、下单、核心配置或硬退出阈值的修改必须人工批准。"
      ]
    }

def main():
    out=build(load(EVIDENCE),load(METHOD),load(PLANNER),load(PREV),load(MODULES),load(EXECUTION),load(CROSS_HISTORY),load(BREADTH_HISTORY),load(REGIME_HISTORY),load(MARKET))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":out["version"],"candidates":len(out["candidates"]),"eligible":len(out["shadow_brain"]["eligible_for_review"])},ensure_ascii=False))
if __name__=="__main__":main()
