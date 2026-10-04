#!/usr/bin/env python3
"""V6.12 Controlled Learning Zone.

Automatically updates research behavior only:
- research-task priority adjustments
- evidence-state labels
- reminder ordering hints

Never mutates production trading rules, thresholds, position sizing or orders.
All adjustments are statelessly recomputed from evidence, bounded, logged and
reversible by deleting this research-policy artifact.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/"docs"/"research"
REPLAY=RESEARCH/"walk_forward_replay.json"
OUTCOME=RESEARCH/"playbook_outcome_shadow.json"
SELF=RESEARCH/"self_improvement.json"
METHOD=RESEARCH/"method_memory.json"
FEEDBACK=RESEARCH/"forward_learning_feedback.json"
PREV=RESEARCH/"controlled_learning_policy.json"
OUT=PREV

VERSION="6.13.2"
MAX_ABS_PRIORITY_DELTA=5.0

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def clip(x,lo,hi):
    return max(lo,min(hi,float(x)))

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def shrink(signal,n,prior=0.0,k=20.0):
    n=max(0.0,float(n or 0))
    s=finite(signal)
    if s is None:return float(prior)
    w=n/(n+k)
    return prior*(1-w)+s*w

def replay_playbook_evidence(replay):
    out={}
    stats=replay.get("statistics") or {}
    grouped={}
    for key,row in stats.items():
        pid=row.get("playbook_id")
        if not pid:continue
        grouped.setdefault(pid,[]).append(row)
    for pid,rows in grouped.items():
        eff=sum(int(r.get("effective_clusters") or 0) for r in rows)
        mature20=[]
        for r in rows:
            h=(r.get("horizons") or {}).get("20") or {}
            if h.get("aligned_rate") is not None:
                mature20.append((int(h.get("effective_n") or 0),float(h["aligned_rate"])))
        denom=sum(n for n,_ in mature20)
        weighted=(sum(n*v for n,v in mature20)/denom) if denom else None
        if eff<20:
            label="replay_early"
        elif weighted is None:
            label="replay_unscored"
        elif weighted>=0.60:
            label="replay_supportive"
        elif weighted<=0.45:
            label="replay_challenging"
        else:
            label="replay_mixed"
        out[pid]={
            "effective_n":eff,
            "alignment20_effective_weighted":weighted,
            "state":label,
            "provenance":"historical_replay_post_rule_design",
        }
    return out

def forward_evidence(outcome):
    by=outcome.get("by_playbook") or {}
    out={}
    for pid,row in by.items():
        h5=((row.get("horizons") or {}).get("5") or {})
        mature=int(h5.get("mature") or 0)
        aligned=int(h5.get("aligned") or 0)
        rate=(aligned/mature) if mature else None
        if mature==0:label="forward_unproven"
        elif mature<5:label="forward_early"
        elif rate is not None and rate>=0.60:label="forward_supportive"
        elif rate is not None and rate<=0.40:label="forward_challenging"
        else:label="forward_mixed"
        out[pid]={"mature5":mature,"aligned5_rate":rate,"state":label,"provenance":"forward_out_of_sample"}
    return out

def candidate_adjustments(self_improvement):
    rows=[]
    for c in self_improvement.get("candidates") or []:
        if c.get("kind")!="research_weight":continue
        proposed=((c.get("proposed_change") or {}).get("priority_weight_delta"))
        if proposed is None:continue
        raw=clip(proposed,-MAX_ABS_PRIORITY_DELTA,MAX_ABS_PRIORITY_DELTA)
        n=int(c.get("evidence_n") or 0)
        shadow_days=int(c.get("shadow_market_days") or 0)
        # Not eligible until both evidence and independent market-day gates pass.
        active=bool(n>=20 and shadow_days>=5)
        applied=shrink(raw,n,k=20.0) if active else 0.0
        rows.append({
            "candidate_id":c.get("candidate_id"),
            "scope":c.get("scope"),
            "raw_delta":raw,
            "applied_delta":round(clip(applied,-MAX_ABS_PRIORITY_DELTA,MAX_ABS_PRIORITY_DELTA),2),
            "evidence_n":n,
            "shadow_market_days":shadow_days,
            "active":active,
            "reason":c.get("reason"),
        })
    return rows

def method_states(method):
    """Mirror Method Memory evidence states; never maintain a parallel taxonomy."""
    out={}
    for m in method.get("methods") or []:
        direct=int(m.get("direct_validated_events") or 0)
        perf=(m.get("performance") or {}).get("20") or {}
        rate=finite(perf.get("alignment_rate"))
        evidence=m.get("evidence_maturity") or {}
        state=evidence.get("state") or m.get("status") or ("context_only" if direct==0 else "direct_early")
        out[m.get("method")]={
            "direct_n":direct,
            "alignment20":rate,
            "state":state,
            "evidence_maturity":evidence,
            "auto_weight_delta":0.0,  # source/method weights remain frozen until a separate policy gate is approved
        }
    return out

def build(replay,outcome,self_improvement,method,feedback=None,previous=None,now=None):
    now=now or datetime.now(timezone.utc)
    replay_ev=replay_playbook_evidence(replay)
    forward_ev=forward_evidence(outcome)
    adjustments=candidate_adjustments(self_improvement)
    methods=method_states(method)

    feedback=feedback or {}
    feedback_playbooks=feedback.get("playbooks") or {}
    feedback_challengers=feedback.get("challengers") or []

    # Controlled task-kind priority modifiers. Only explicitly mapped research
    # scopes can move; all unlisted kinds receive zero adjustment.
    task_kind_delta={}
    scope_to_kind={
        "cross_asset_divergence":"cross_asset_divergence",
        "breadth_intelligence":"breadth_intelligence",
        "regime_combination":"regime_combination",
    }
    for a in adjustments:
        kind=scope_to_kind.get(a["scope"])
        if kind and a["active"]:
            task_kind_delta[kind]=round(clip(task_kind_delta.get(kind,0)+a["applied_delta"],-MAX_ABS_PRIORITY_DELTA,MAX_ABS_PRIORITY_DELTA),2)

    # Replay strength only changes validation/review ordering, never trading.
    playbook_validation_priority={}
    for pid,r in replay_ev.items():
        eff=int(r.get("effective_n") or 0)
        f=forward_ev.get(pid,{})
        f5=int(f.get("mature5") or 0)
        uncertainty_bonus=5 if f5==0 else 3 if f5<5 else 0
        replay_bonus=2 if eff>=50 else 1 if eff>=20 else 0
        feedback_state=(feedback_playbooks.get(pid) or {}).get("state")
        feedback_bonus=3 if feedback_state in {"forward_challenging","data_quality_review"} else 2 if feedback_state=="forward_mixed" else 0
        challenger_bonus=2 if any(x.get("playbook_id")==pid and x.get("state")=="shadow_candidate" for x in feedback_challengers) else 0
        playbook_validation_priority[pid]=min(10,uncertainty_bonus+replay_bonus+feedback_bonus+challenger_bonus)

    prev=previous or {}
    prev_gen=prev.get("generated_at")
    return {
        "version":VERSION,
        "generated_at":now.astimezone(timezone.utc).isoformat(),
        "mode":"controlled_research_only",
        "production_mutation":False,
        "automatic_orders":False,
        "max_abs_priority_delta":MAX_ABS_PRIORITY_DELTA,
        "task_kind_priority_delta":task_kind_delta,
        "playbook_validation_priority_bonus":playbook_validation_priority,
        "replay_evidence":replay_ev,
        "forward_evidence":forward_ev,
        "method_evidence_state":methods,
        "candidate_adjustments":adjustments,
        "forward_learning_feedback":{
            "mode":feedback.get("mode"),
            "counts":feedback.get("counts") or {},
            "playbook_states":{pid:(row or {}).get("state") for pid,row in feedback_playbooks.items()},
            "challenger_candidates":[{"challenger_id":x.get("challenger_id"),"playbook_id":x.get("playbook_id"),"state":x.get("state")} for x in feedback_challengers],
            "automatic_promotion":False,
        },
        "change_log":{
            "previous_generated_at":prev_gen,
            "recomputed_from_current_evidence":True,
            "cumulative_same_day_learning":False,
            "rollback":"delete/ignore controlled_learning_policy.json to return all controlled deltas to zero",
        },
        "guardrails":[
            "Only research ordering, evidence labels and reminder priority may change automatically.",
            "All research-priority deltas are bounded to +/-5 points.",
            "Repeated workflows on the same market day do not accumulate deltas.",
            "Historical replay and Forward evidence remain separately labeled.",
            "Method/source weights remain frozen even after maturity labels change; a separate approved policy gate is required.",
            "Production thresholds, Hard Exit, position sizing, portfolio allocation and order logic are immutable here.",
        ],
    }

def main():
    out=build(load(REPLAY),load(OUTCOME),load(SELF),load(METHOD),load(FEEDBACK),load(PREV))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "version":out["version"],
        "task_kind_priority_delta":out["task_kind_priority_delta"],
        "playbook_validation_priority_bonus":out["playbook_validation_priority_bonus"],
        "active_adjustments":sum(1 for x in out["candidate_adjustments"] if x["active"]),
    },ensure_ascii=False))

if __name__=="__main__":
    main()
