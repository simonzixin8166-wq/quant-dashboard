#!/usr/bin/env python3
"""Mature outcome scorecards for Cross-Asset, Breadth and Regime histories."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CROSS=ROOT/"docs"/"research"/"cross_asset_divergence_history.json"
BREADTH=ROOT/"docs"/"research"/"breadth_intelligence_history.json"
REGIME=ROOT/"docs"/"research"/"regime_combination_history.json"
OUT=ROOT/"docs"/"research"/"market_state_outcome_scorecards.json"
ARCH=ROOT/"research"/"archive"/"market_state_outcomes.jsonl"
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive

H=(5,20,60)

def load(p):
    try:return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:return {}

def key(kind,row,h):
    ident=row.get("state_id") or row.get("combination_key") or row.get("level") or row.get("label") or "state"
    return f"{kind}|{row.get('as_of')}|{ident}|{h}"

def outcome(kind,row,h,spy):
    try:d=pd.Timestamp(str(row.get("as_of"))[:10])
    except Exception:return None
    fut=spy[spy.index>d].sort_index().head(h)
    if len(fut)<h:return None
    px=float(row.get("anchor_spy") or 0)
    if px<=0:return None
    closes=fut["close"].astype(float);highs=fut["high"].astype(float);lows=fut["low"].astype(float)
    state=row.get("state_id") or row.get("combination_key") or row.get("level") or row.get("label")
    return {
      "outcome_id":key(kind,row,h),"kind":kind,"as_of":str(row.get("as_of"))[:10],
      "state":state,"level":row.get("level"),"horizon_sessions":h,
      "horizon_end":str(fut.index[-1])[:10],
      "return_pct":float(closes.iloc[-1]/px-1)*100,
      "mae_pct":float(lows.min()/px-1)*100,
      "mfe_pct":float(highs.max()/px-1)*100,
      "matured_at":datetime.now(timezone.utc).isoformat(),"production_effect":"none",
    }

def existing_ids():
    out=set()
    if ARCH.exists():
        for line in ARCH.read_text(encoding="utf-8").splitlines():
            try:out.add(str(json.loads(line).get("outcome_id")))
            except Exception:pass
    return out

def append(rows):
    if not rows:return 0
    ARCH.parent.mkdir(parents=True,exist_ok=True)
    known=existing_ids();n=0
    with ARCH.open("a",encoding="utf-8") as f:
        for row in rows:
            if row["outcome_id"] in known:continue
            f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
            known.add(row["outcome_id"]);n+=1
    return n

def all_outcomes():
    rows=[]
    if not ARCH.exists():return rows
    for line in ARCH.read_text(encoding="utf-8").splitlines():
        try:rows.append(json.loads(line))
        except Exception:pass
    return rows

def build_scorecards(rows):
    groups={}
    for r in rows:
        k=(r["kind"],str(r.get("state")),int(r["horizon_sessions"]))
        groups.setdefault(k,[]).append(r)
    cards=[]
    for (kind,state,h),xs in sorted(groups.items()):
        cards.append({
          "kind":kind,"state":state,"horizon_sessions":h,"n":len(xs),
          "avg_return_pct":sum(x["return_pct"] for x in xs)/len(xs),
          "avg_mae_pct":sum(x["mae_pct"] for x in xs)/len(xs),
          "avg_mfe_pct":sum(x["mfe_pct"] for x in xs)/len(xs),
          "positive_rate":sum(x["return_pct"]>0 for x in xs)/len(xs),
        })
    return cards

def run(hist=None):
    hist=hist or read_archive();spy=hist.get("SPY")
    if spy is None:
        rows=all_outcomes()
        out={"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
             "status":"waiting_for_market_history",
             "counts":{"outcomes":len(rows),"added":0,"scorecards":len(build_scorecards(rows))},
             "scorecards":build_scorecards(rows),
             "guardrails":["Missing local market history fails closed for maturation without blocking unrelated source learning.","No synthetic outcomes are created.","Research evaluation only; no Production rule mutation."]}
        OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return out
    candidates=[]
    for kind,path in (("cross_asset",CROSS),("breadth",BREADTH),("regime",REGIME)):
        for row in load(path).get("records") or []:
            for h in H:
                o=outcome(kind,row,h,spy)
                if o:candidates.append(o)
    added=append(candidates)
    rows=all_outcomes()
    out={
      "version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "status":"learning_active" if rows else "waiting_for_mature_outcomes",
      "counts":{"outcomes":len(rows),"added":added,"scorecards":len(build_scorecards(rows))},
      "scorecards":build_scorecards(rows),
      "guardrails":["Historical state snapshots are never rewritten.","Only completed future SPY sessions mature outcomes.","Research evaluation only; no Production rule mutation."]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False))
