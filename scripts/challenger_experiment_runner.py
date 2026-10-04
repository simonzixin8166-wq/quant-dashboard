#!/usr/bin/env python3
"""V6.13 Challenger Experiment Runner (research-only).

Pre-registers diagnostic shadow experiments only after Forward Learning emits a
real challenger candidate. It never invents challengers from Replay alone.

This first stage deliberately separates:
1) candidate gate
2) immutable experiment specification
3) baseline evidence snapshot
4) execution readiness

No production rule mutation, no automatic promotion and no order path exist.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/"docs"/"research"
FEEDBACK=RESEARCH/"forward_learning_feedback.json"
REPLAY=RESEARCH/"walk_forward_replay.json"
PREV=RESEARCH/"challenger_experiments.json"
OUT=PREV
VERSION="6.13.0"

CATALOG={
    "CP-01":[
        {
            "experiment_key":"state_detail_separation",
            "hypothesis":"不同回撤档位可能具有不同前瞻质量；先分层验证，不合并成单一胜率。",
            "variant":"evaluate_each_existing_tier_separately",
            "changes_production_rule":False,
        },
        {
            "experiment_key":"confirmation_delay_1_session",
            "hypothesis":"增加一交易日确认可能减少短暂回撤触发，但会牺牲更早入场。",
            "variant":"research_only_one_session_confirmation",
            "changes_production_rule":False,
        },
    ],
    "CP-02":[
        {
            "experiment_key":"risk_direction_separation",
            "hypothesis":"降风险与恢复风险属于相反目标，必须分别评价而不是合并胜率。",
            "variant":"separate_risk_reduction_and_risk_restore",
            "changes_production_rule":False,
        },
        {
            "experiment_key":"state_detail_separation",
            "hypothesis":"hard_exit/tier2/tier1/restore 的历史质量可能不同；先定位薄弱状态，不直接改阈值。",
            "variant":"evaluate_each_existing_action_state_separately",
            "changes_production_rule":False,
        },
    ],
    "CP-03":[
        {
            "experiment_key":"candidate_strong_separation",
            "hypothesis":"candidate 与 strong 的前瞻质量可能不同，应分别验证。",
            "variant":"evaluate_candidate_and_strong_separately",
            "changes_production_rule":False,
        },
        {
            "experiment_key":"risk_context_stratification",
            "hypothesis":"同一 LEAPS 市场条件在 trend_risk / vix_risk 环境下可能表现不同。",
            "variant":"stratify_existing_signals_by_risk_context",
            "changes_production_rule":False,
        },
    ],
}

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def experiment_id(challenger_id,key):
    return hashlib.sha256(f"{challenger_id}|{key}|v1".encode()).hexdigest()[:16]

def baseline_for(pid,replay):
    rows=[]
    for _,row in (replay.get("statistics") or {}).items():
        if row.get("playbook_id")!=pid:continue
        h20=((row.get("horizons") or {}).get("20") or {})
        rows.append({
            "state_detail":row.get("state_detail"),
            "raw_events":int(row.get("raw_events") or 0),
            "effective_clusters":int(row.get("effective_clusters") or 0),
            "mature20_raw_n":int(h20.get("raw_n") or 0),
            "mature20_effective_n":int(h20.get("effective_n") or 0),
            "aligned_rate20":h20.get("aligned_rate"),
            "avg_return20":h20.get("avg_return"),
            "avg_mae20":h20.get("avg_mae"),
            "avg_mfe20":h20.get("avg_mfe"),
        })
    return sorted(rows,key=lambda x:str(x.get("state_detail") or ""))

def build(feedback,replay,previous=None,now=None):
    now=now or datetime.now(timezone.utc)
    candidates=[
        x for x in (feedback.get("challengers") or [])
        if x.get("state")=="shadow_candidate"
        and x.get("human_review_required") is True
    ]
    experiments=[]
    for candidate in candidates:
        pid=candidate.get("playbook_id")
        cid=candidate.get("challenger_id")
        base=baseline_for(pid,replay)
        for spec in CATALOG.get(pid,[]):
            eid=experiment_id(cid,spec["experiment_key"])
            effective=sum(x["mature20_effective_n"] for x in base)
            experiments.append({
                "experiment_id":eid,
                "challenger_id":cid,
                "playbook_id":pid,
                "state":"preregistered_shadow",
                "experiment_key":spec["experiment_key"],
                "hypothesis":spec["hypothesis"],
                "variant":spec["variant"],
                "baseline_snapshot":{
                    "provenance":"historical_replay_post_rule_design",
                    "effective_n20":effective,
                    "by_state_detail":base,
                },
                "minimum_gate":{
                    "forward_mature20_required":3,
                    "historical_effective_n20_required":20,
                    "current_historical_effective_n20":effective,
                },
                "execution":{
                    "ready":effective>=20,
                    "result_status":"not_run" if effective>=20 else "insufficient_history",
                    "result":None,
                },
                "frozen_spec":True,
                "changes_production_rule":False,
                "automatic_promotion":False,
                "human_review_required":True,
            })

    return {
        "version":VERSION,
        "generated_at":now.astimezone(timezone.utc).isoformat(),
        "mode":"preregistered_shadow_research_only",
        "source_feedback_version":feedback.get("version"),
        "source_replay_version":replay.get("version"),
        "candidate_count":len(candidates),
        "experiment_count":len(experiments),
        "experiments":experiments,
        "status":"waiting_for_real_forward_challenger" if not candidates else "shadow_experiments_preregistered",
        "guardrails":[
            "Replay alone cannot create a Challenger candidate.",
            "Experiments are created only from Forward-gated challenger candidates.",
            "Experiment specifications are frozen before result generation.",
            "Historical replay remains historical_replay_post_rule_design and never becomes Forward evidence.",
            "No production threshold, Hard Exit, position size, allocation or order behavior can be changed here.",
            "No challenger can be automatically promoted.",
        ],
    }

def main():
    out=build(load(FEEDBACK),load(REPLAY),load(PREV))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "version":out["version"],
        "status":out["status"],
        "candidate_count":out["candidate_count"],
        "experiment_count":out["experiment_count"],
    },ensure_ascii=False))

if __name__=="__main__":
    main()
