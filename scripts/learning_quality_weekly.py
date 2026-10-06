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
    snapshot={}
    changes=[]
    attention=[]
    for name in ("market","fundamental","event","options","decision"):
        row=eq.get(name) or {}
        numeric={k:v for k,v in row.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        snapshot[name]={"validation_state":row.get("validation_state"),"feedback_state":row.get("feedback_state"),"numeric":numeric}
        old=(prev_snapshot.get(name) or {}).get("numeric") or {}
        deltas={k:v-old.get(k,0) for k,v in numeric.items() if isinstance(old.get(k,0),(int,float)) and v!=old.get(k,0)}
        if deltas:changes.append({"engine":name,"numeric_deltas":deltas})
        state=str(row.get("validation_state") or "")
        if any(x in state for x in ("missing","unproven","partial","descriptive","no_samples")):
            attention.append({"engine":name,"state":state,"gap":row.get("gap")})
    iso=now.isocalendar()
    return {
      "version":"learning-quality-weekly-1",
      "generated_at":now.isoformat(),
      "week":f"{iso.year}-W{iso.week:02d}",
      "learning_health":current.get("learning_health") or {},
      "snapshot":snapshot,
      "changes_since_previous_report":changes,
      "attention":attention,
      "principle":"只汇总真实证据成熟度和样本变化；不把活动量、历史回放或模拟结果冒充 Forward/Outcome Learning。",
    }

def main():
    current=load(SRC);previous=load(OUT)
    out=build(current,previous)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"week":out["week"],"changes":len(out["changes_since_previous_report"]),"attention":len(out["attention"])},ensure_ascii=False))

if __name__=="__main__":main()
