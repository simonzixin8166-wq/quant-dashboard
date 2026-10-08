#!/usr/bin/env python3
"""Point-in-time macro regime observation -> future market outcome memory."""
from __future__ import annotations
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CURRENT=ROOT/"docs"/"research"/"macro_context.json"
OBS=ROOT/"research"/"archive"/"macro_regime_observations.jsonl"
OUTCOMES=ROOT/"research"/"archive"/"macro_regime_outcomes.jsonl"
OUT=ROOT/"docs"/"research"/"macro_outcome_memory.json"
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive
H=(5,20,60)

def load(p,d=None):
    try:return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:return {} if d is None else d

def regime_key(reg):
    fields=["rates_regime","real_yield_regime","yield_curve","inflation_regime","credit_regime","financial_conditions"]
    return "|".join(str(reg.get(x) or "NA") for x in fields)

def obs_id(asof,key):
    return hashlib.sha256(f"{asof}|{key}".encode()).hexdigest()[:24]

def append(path,row,idkey):
    path.parent.mkdir(parents=True,exist_ok=True)
    known=set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:known.add(str(json.loads(line).get(idkey)))
            except Exception:pass
    if str(row[idkey]) in known:return False
    with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    return True

def read_all(path):
    rows=[]
    if not path.exists():return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:rows.append(json.loads(line))
        except Exception:pass
    return rows

def snapshot(doc):
    reg=doc.get("regime") or {};asof=str(doc.get("as_of") or "")[:10]
    if not asof or not reg:return None
    key=regime_key(reg)
    return {
      "observation_id":obs_id(asof,key),"as_of":asof,"observed_at":doc.get("generated_at"),
      "regime_key":key,"macro_risk_score":reg.get("macro_risk_score"),
      "regime":{k:v for k,v in reg.items() if k!="components"},
      "quality":doc.get("quality") or {},"point_in_time_capable":doc.get("point_in_time_capable"),
      "production_effect":"none",
    }

def mature(obs,spy,h):
    try:d=pd.Timestamp(obs["as_of"])
    except Exception:return None
    base=spy[spy.index<=d].sort_index()
    if base.empty:return None
    px=float(base["close"].iloc[-1])
    fut=spy[spy.index>d].sort_index().head(h)
    if len(fut)<h:return None
    closes=fut["close"].astype(float);highs=fut["high"].astype(float);lows=fut["low"].astype(float)
    return {
      "outcome_id":f"{obs['observation_id']}:{h}","observation_id":obs["observation_id"],
      "as_of":obs["as_of"],"regime_key":obs["regime_key"],"macro_risk_score":obs.get("macro_risk_score"),
      "horizon_sessions":h,"horizon_end":str(fut.index[-1])[:10],
      "spy_return_pct":float(closes.iloc[-1]/px-1)*100,
      "mae_pct":float(lows.min()/px-1)*100,"mfe_pct":float(highs.max()/px-1)*100,
      "matured_at":datetime.now(timezone.utc).isoformat(),"production_effect":"none",
    }

def scorecards(rows):
    groups={}
    for r in rows:groups.setdefault((r["regime_key"],r["horizon_sessions"]),[]).append(r)
    out=[]
    for (key,h),xs in sorted(groups.items()):
        out.append({"regime_key":key,"horizon_sessions":h,"n":len(xs),
                    "avg_spy_return_pct":sum(x["spy_return_pct"] for x in xs)/len(xs),
                    "avg_mae_pct":sum(x["mae_pct"] for x in xs)/len(xs),
                    "avg_mfe_pct":sum(x["mfe_pct"] for x in xs)/len(xs),
                    "positive_rate":sum(x["spy_return_pct"]>0 for x in xs)/len(xs)})
    return out

def run(doc=None,hist=None):
    doc=doc or load(CURRENT,{})
    row=snapshot(doc);added_obs=0
    if row:added_obs=int(append(OBS,row,"observation_id"))
    hist=hist if hist is not None else read_archive();spy=hist.get("SPY")
    if spy is None:raise SystemExit("SPY history missing")
    known={x["outcome_id"] for x in read_all(OUTCOMES) if x.get("outcome_id")}
    added=0
    for obs in read_all(OBS):
        for h in H:
            x=mature(obs,spy,h)
            if x and x["outcome_id"] not in known and append(OUTCOMES,x,"outcome_id"):
                known.add(x["outcome_id"]);added+=1
    rows=read_all(OUTCOMES)
    out={"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
         "status":"learning_active" if rows else "waiting_for_mature_outcomes",
         "counts":{"observations":len(read_all(OBS)),"observations_added":added_obs,"outcomes":len(rows),"outcomes_added":added,"scorecards":len(scorecards(rows))},
         "scorecards":scorecards(rows),
         "guardrails":["Macro observations preserve the point-in-time snapshot/vintage context.","Only completed future SPY sessions mature outcomes.","Research evaluation only; no Production rule mutation."]}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False))
