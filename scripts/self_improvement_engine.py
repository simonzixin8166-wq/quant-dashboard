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

def build(evidence,method,planner,previous,modules=None):
    candidates=[]
    for m in method.get("methods") or []:
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
    failn=len(f.get("external_outcome_reviews") or [])
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
    old={x.get("candidate_id"):x for x in previous.get("candidates") or []}
    promoted=[];shadow=[]
    for c in candidates:
        prior=old.get(c["candidate_id"],{})
        runs=(prior.get("shadow_runs") or 0)+1
        c["shadow_runs"]=runs
        c["first_seen_at"]=prior.get("first_seen_at") or c["created_at"]
        # Conservative automatic gate: research-process changes only, >=20 evidence,
        # >=5 independent shadow runs; never production trading thresholds.
        eligible=(c["evidence_n"]>=20 and runs>=5 and c["kind"] in {"research_weight","process_guardrail"})
        c["promotion_eligible"]=eligible
        c["state"]="eligible_for_review" if eligible else "shadow"
        shadow.append(c)
        if eligible: promoted.append(c["candidate_id"])

    return {
      "version":"7.1.0","generated_at":datetime.now(timezone.utc).isoformat(),
      "production_brain":{"mode":"locked","rule":"正式交易阈值与仓位规则不由本引擎自动修改。"},
      "learning_brain":{"planner_version":planner.get("version"),"open_tasks":(planner.get("counts") or {}).get("open",0)},
      "candidate_brain":{"count":len(shadow)},
      "shadow_brain":{"candidates":shadow,"eligible_for_review":promoted},
      "promotion_gate":{
        "automatic_production_promotion":False,
        "minimum_evidence_n":20,"minimum_shadow_runs":5,
        "allowed_scope":["research_priority","research_process"],
        "forbidden_scope":["orders","position_size","core_allocation","hard_exit_thresholds"],
        "decision":"human_review_required"
      },
      "candidates":shadow,
      "guardrails":[
        "候选策略只能在 Shadow 模式积累证据。",
        "达到门槛仅代表可复核，不自动晋级正式交易规则。",
        "任何涉及仓位、下单、核心配置或硬退出阈值的修改必须人工批准。"
      ]
    }

def main():
    out=build(load(EVIDENCE),load(METHOD),load(PLANNER),load(PREV),load(MODULES))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":out["version"],"candidates":len(out["candidates"]),"eligible":len(out["shadow_brain"]["eligible_for_review"])},ensure_ascii=False))
if __name__=="__main__":main()
