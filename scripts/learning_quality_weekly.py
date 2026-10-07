#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"docs/research/learning_evaluation.json"
OUT=ROOT/"docs/research/learning_quality_weekly.json"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def build(current,previous=None,now=None):
    previous=previous or {}
    now=now or datetime.now(timezone.utc)
    eq=current.get("engine_quality") or {}
    prev_snapshot=previous.get("snapshot") or {}
    baseline_report=not bool(prev_snapshot)
    snapshot={}
    changes=[]
    attention=[]
    for name in ("market","fundamental","event","options","decision"):
        row=eq.get(name) or {}
        numeric={k:v for k,v in row.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        snapshot[name]={"validation_state":row.get("validation_state"),"feedback_state":row.get("feedback_state"),"numeric":numeric}
        old=(prev_snapshot.get(name) or {}).get("numeric") or {}
        deltas={}
        if not baseline_report:
            for k,v in numeric.items():
                if k.startswith("historical_") or k not in old:continue
                if isinstance(old.get(k),(int,float)) and v!=old[k]:deltas[k]=v-old[k]
        if deltas:changes.append({"engine":name,"numeric_deltas":deltas})
        state=str(row.get("validation_state") or "")
        numeric_gaps=[]
        if name=="market":
            if int(row.get("forward_mature_20") or 0)==0:numeric_gaps.append("forward_mature_20=0")
            if int(row.get("forward_mature_60") or 0)==0:numeric_gaps.append("forward_mature_60=0")
        elif name=="fundamental" and int(row.get("outcome_mature_60") or 0)<=1:numeric_gaps.append("60d_outcomes_early")
        elif name=="options" and int(row.get("mature_outcomes") or 0)==0:numeric_gaps.append("mature_outcomes=0")
        elif name=="decision" and int(row.get("with_user_action") or 0)==0:numeric_gaps.append("with_user_action=0")
        if any(x in state for x in ("missing","unproven","partial","descriptive","no_samples")) or numeric_gaps:
            attention.append({"engine":name,"state":state,"gap":row.get("gap"),"numeric_gaps":numeric_gaps})
    iso=now.isocalendar()
    return {
      "version":"learning-quality-weekly-1.1",
      "generated_at":now.isoformat(),
      "week":f"{iso.year}-W{iso.week:02d}",
      "baseline_report":baseline_report,
      "learning_health":current.get("learning_health") or {},
      "snapshot":snapshot,
      "changes_since_previous_report":changes,
      "attention":attention,
      "principle":"只汇总真实证据成熟度和样本变化；首次报告只建立 baseline，不制造 delta；historical_* 不计入周变化；未成熟项按真实数字持续进入 attention，不把活动量冒充 Forward/Outcome Learning。",
    }

def main():
    current=load(SRC);previous=load(OUT)
    out=build(current,previous)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"week":out["week"],"baseline":out["baseline_report"],"changes":len(out["changes_since_previous_report"]),"attention":len(out["attention"])},ensure_ascii=False))

if __name__=="__main__":main()
