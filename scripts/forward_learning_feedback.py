#!/usr/bin/env python3
"""V6.12.1 Forward Learning Feedback + Challenger Shadow.

Consumes sanitized Forward Outcome aggregates and historical Replay evidence.
Produces only anonymous/playbook-level research feedback:
- Forward evidence maturity and failure-attribution summaries
- Replay-vs-Forward agreement/divergence
- Challenger candidates for human review

It never reads raw private ledger records directly, never changes production
rules, never places orders, and never promotes a challenger automatically.
"""
from __future__ import annotations
import json, math, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/"docs"/"research"
OUTCOME=RESEARCH/"playbook_outcome_shadow.json"
REPLAY=RESEARCH/"walk_forward_replay.json"
PREV=RESEARCH/"forward_learning_feedback.json"
OUT=PREV
VERSION="6.12.1"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def rate(h):
    m=int((h or {}).get("mature") or 0)
    a=int((h or {}).get("aligned") or 0)
    return (a/m) if m else None

def replay_map(replay):
    grouped={}
    for _,row in (replay.get("statistics") or {}).items():
        pid=row.get("playbook_id")
        if not pid:continue
        h20=((row.get("horizons") or {}).get("20") or {})
        n=int(h20.get("effective_n") or 0)
        r=finite(h20.get("aligned_rate"))
        if n and r is not None:
            grouped.setdefault(pid,[]).append((n,r,row.get("state_detail")))
    out={}
    for pid,rows in grouped.items():
        denom=sum(n for n,_,_ in rows)
        out[pid]={
            "effective_n20":denom,
            "aligned_rate20":sum(n*r for n,r,_ in rows)/denom if denom else None,
            "details":[{"state_detail":d,"effective_n20":n,"aligned_rate20":r} for n,r,d in rows],
            "provenance":"historical_replay_post_rule_design",
        }
    return out

def classify_forward(row):
    h5=((row.get("horizons") or {}).get("5") or {})
    h20=((row.get("horizons") or {}).get("20") or {})
    h60=((row.get("horizons") or {}).get("60") or {})
    m5=int(h5.get("mature") or 0); r5=rate(h5)
    m20=int(h20.get("mature") or 0); r20=rate(h20)
    m60=int(h60.get("mature") or 0); r60=rate(h60)
    q=int(row.get("baseline_mismatch") or 0)+int(row.get("history_or_definition_missing") or 0)
    timing=int(row.get("timing_uncertain") or 0)
    if q>0:return "data_quality_review"
    if m5==0:return "forward_unproven"
    if m20<3:return "forward_early"
    basis=r20 if r20 is not None else r5
    if basis is None:return "forward_unscored"
    if basis>=0.60:return "forward_supportive"
    if basis<=0.40:return "forward_challenging"
    return "forward_mixed"

def attribution(pid,row,replay_row):
    out=[]
    h20=((row.get("horizons") or {}).get("20") or {})
    mature20=int(h20.get("mature") or 0)
    aligned20=int(h20.get("aligned") or 0)
    r20=(aligned20/mature20) if mature20 else None
    mismatch=int(row.get("baseline_mismatch") or 0)
    uncertain=int(row.get("timing_uncertain") or 0)
    if mismatch:
        out.append({
            "tag":"baseline_integrity",
            "severity":"review",
            "evidence_n":mismatch,
            "hypothesis":"存在 Forward baseline 与本地历史不一致样本；先排查复权/数据源一致性，不评价规则优劣。",
        })
    if uncertain:
        out.append({
            "tag":"late_detection_timing",
            "severity":"review",
            "evidence_n":uncertain,
            "hypothesis":"存在检测时点不确定样本；先隔离时点误差，不能把它当成规则本身失败。",
        })
    if mature20>=3 and r20 is not None and r20<=0.40:
        out.append({
            "tag":"forward_direction_challenging",
            "severity":"review",
            "evidence_n":mature20,
            "hypothesis":"20日 Forward 方向一致率偏低；需要检查触发条件是否过宽、状态持续时间或环境依赖。",
        })
    rr=(replay_row or {}).get("aligned_rate20")
    rn=int((replay_row or {}).get("effective_n20") or 0)
    if mature20>=3 and r20 is not None and rr is not None and rn>=20 and abs(r20-rr)>=0.20:
        out.append({
            "tag":"replay_forward_divergence",
            "severity":"review",
            "evidence_n":mature20,
            "hypothesis":"Forward 与历史 Replay 的20日方向一致率出现明显偏离；优先检查市场环境差异、样本聚类与状态定义，不自动改阈值。",
        })
    return out

def challenger_id(pid,kind):
    return hashlib.sha1(f"{pid}|{kind}".encode()).hexdigest()[:14]

def build(outcome,replay,previous=None,now=None):
    now=now or datetime.now(timezone.utc)
    rmap=replay_map(replay)
    playbooks={}
    challengers=[]
    for pid,row in sorted((outcome.get("by_playbook") or {}).items()):
        rep=rmap.get(pid) or {}
        state=classify_forward(row)
        attrs=attribution(pid,row,rep)
        h5=((row.get("horizons") or {}).get("5") or {})
        h20=((row.get("horizons") or {}).get("20") or {})
        h60=((row.get("horizons") or {}).get("60") or {})
        f={
            "state":state,
            "forward_provenance":"forward_out_of_sample",
            "replay_provenance":rep.get("provenance"),
            "trigger_records":int(row.get("trigger_records") or 0),
            "mature5":int(h5.get("mature") or 0),
            "mature20":int(h20.get("mature") or 0),
            "mature60":int(h60.get("mature") or 0),
            "aligned_rate5":rate(h5),
            "aligned_rate20":rate(h20),
            "aligned_rate60":rate(h60),
            "baseline_mismatch":int(row.get("baseline_mismatch") or 0),
            "timing_uncertain":int(row.get("timing_uncertain") or 0),
            "replay_effective_n20":int(rep.get("effective_n20") or 0),
            "replay_aligned_rate20":rep.get("aligned_rate20"),
            "attribution":attrs,
            "by_state_detail":row.get("by_state_detail") or {},
        }
        playbooks[pid]=f

        review_tags=[x["tag"] for x in attrs]
        eligible_for_shadow=(
            int(h20.get("mature") or 0)>=3
            and ("forward_direction_challenging" in review_tags or "replay_forward_divergence" in review_tags)
            and int(row.get("baseline_mismatch") or 0)==0
        )
        if eligible_for_shadow:
            challengers.append({
                "challenger_id":challenger_id(pid,"review"),
                "playbook_id":pid,
                "state":"shadow_candidate",
                "reason_tags":review_tags,
                "proposal_scope":"diagnostic_only",
                "allowed_actions":[
                    "compare alternative environment filters",
                    "compare state-duration / cooldown variants",
                    "compare stricter confirmation in historical replay",
                ],
                "forbidden_actions":[
                    "change production threshold",
                    "change Hard Exit",
                    "change position size",
                    "place order",
                    "automatic promotion",
                ],
                "human_review_required":True,
            })

    previous=previous or {}
    return {
        "version":VERSION,
        "generated_at":now.astimezone(timezone.utc).isoformat(),
        "mode":"shadow_research_only",
        "playbooks":playbooks,
        "challengers":challengers,
        "counts":{
            "playbooks":len(playbooks),
            "challenger_candidates":len(challengers),
            "forward_mature20":sum(x["mature20"] for x in playbooks.values()),
            "forward_mature60":sum(x["mature60"] for x in playbooks.values()),
            "attribution_reviews":sum(len(x["attribution"]) for x in playbooks.values()),
        },
        "change_log":{
            "previous_generated_at":previous.get("generated_at"),
            "stateless_recompute":True,
            "automatic_promotion":False,
        },
        "guardrails":[
            "Only sanitized aggregate Forward outcome data is consumed.",
            "No raw private record identifiers, account positions or ledger hashes are published.",
            "Attribution entries are hypotheses for research, not proven causes.",
            "Challengers remain shadow candidates and require human review.",
            "Production thresholds, Hard Exit, position sizing, allocation and order logic remain immutable.",
        ],
    }

def main():
    out=build(load(OUTCOME),load(REPLAY),load(PREV))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "version":out["version"],
        "counts":out["counts"],
        "challengers":[x["playbook_id"] for x in out["challengers"]],
    },ensure_ascii=False))

if __name__=="__main__":
    main()
