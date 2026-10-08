#!/usr/bin/env python3
"""Outcome memory for research-only Options Opportunity context.

Freezes every daily scan/reject/no-trade state and later matures underlying
5/20-session outcomes. It evaluates research triage quality only; it never
simulates option PnL and never mutates Production rules.
"""
from __future__ import annotations
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CURRENT=ROOT/"docs"/"research"/"options_opportunity_context.json"
OBS=ROOT/"research"/"archive"/"options_opportunity_observations"
OUTCOMES=ROOT/"research"/"archive"/"options_opportunity_outcomes"
OUT=ROOT/"docs"/"research"/"options_opportunity_outcome_memory.json"
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive

HORIZONS=(5,20)

def load(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def asof_from_context(row):
    # Underlying price/support artifact is completed-daily context.
    return str(row.get("as_of") or ((row.get("context") or {}).get("as_of")) or "")[:10]

def key(symbol,asof,state,reasons):
    raw="|".join([symbol,asof,str(state),"|".join(sorted(reasons or []))])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def append(path,row,idkey):
    path.parent.mkdir(parents=True,exist_ok=True)
    known=set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:known.add(str(json.loads(line).get(idkey)))
            except Exception:pass
    if str(row.get(idkey)) in known:return False
    with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    return True

def snapshot_rows(doc):
    rows=[]
    generated=doc.get("generated_at")
    for symbol,row in (doc.get("records") or {}).items():
        ctx=row.get("context") or {}
        # Current artifact lacks a top-level as_of; infer from the support
        # source only when explicitly carried, otherwise use generated date
        # for research observation timing and never backdate.
        asof=asof_from_context(row) or str(generated or "")[:10]
        reasons=list(row.get("reasons") or [])
        obs={
          "observation_id":key(symbol,asof,row.get("state"),reasons),
          "symbol":symbol,"observed_at":generated,"as_of":asof,
          "state":row.get("state"),"status":row.get("status"),
          "scan_priority":row.get("scan_priority"),"scan_lanes":row.get("scan_lanes") or [],
          "research_modes":row.get("research_modes") or [],
          "reasons":reasons,
          "price":ctx.get("price"),"rsi14":ctx.get("rsi14"),
          "near_strong_support":ctx.get("near_strong_support"),
          "forecast_vol_expanding":ctx.get("forecast_vol_expanding"),
          "trend_constructive":ctx.get("trend_constructive"),
          "structurally_weak":ctx.get("structurally_weak"),
          "required_before_strategy_candidate":row.get("required_before_strategy_candidate") or [],
          "trade_action":None,"production_effect":"none",
        }
        rows.append(obs)
    return rows

def read_all(folder):
    rows=[]
    if not folder.exists():return rows
    for p in folder.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:rows.append(json.loads(line))
            except Exception:pass
    return rows

def mature(obs,df,h):
    if df is None or df.empty:return None
    try:day=pd.Timestamp(str(obs["as_of"])[:10])
    except Exception:return None
    fut=df[df.index>day].sort_index().head(h)
    if len(fut)<h:return None
    px=float(obs.get("price") or 0)
    if px<=0:return None
    closes=fut["close"].astype(float);highs=fut["high"].astype(float);lows=fut["low"].astype(float)
    return {
      "outcome_id":f"{obs['observation_id']}:{h}",
      "observation_id":obs["observation_id"],"symbol":obs["symbol"],
      "as_of":obs["as_of"],"horizon_sessions":h,
      "horizon_end":str(fut.index[-1])[:10],
      "underlying_return_pct":float(closes.iloc[-1]/px-1)*100,
      "mae_pct":float(lows.min()/px-1)*100,
      "mfe_pct":float(highs.max()/px-1)*100,
      "original_state":obs.get("state"),"original_priority":obs.get("scan_priority"),
      "original_reasons":obs.get("reasons") or [],
      "production_effect":"none",
      "matured_at":datetime.now(timezone.utc).isoformat(),
    }

def run(doc=None,hist=None):
    doc=doc or load(CURRENT,{})
    hist=hist if hist is not None else read_archive()
    added_obs=0
    for row in snapshot_rows(doc):
        p=OBS/f"{str(row['as_of'])[:7]}.jsonl"
        added_obs+=int(append(p,row,"observation_id"))
    existing={str(x.get("outcome_id")) for x in read_all(OUTCOMES)}
    added_out=0;matured=[]
    for obs in read_all(OBS):
        for h in HORIZONS:
            result=mature(obs,hist.get(obs.get("symbol")),h)
            if not result:continue
            matured.append(result)
            if result["outcome_id"] not in existing:
                p=OUTCOMES/f"{str(result['horizon_end'])[:7]}.jsonl"
                if append(p,result,"outcome_id"):
                    added_out+=1;existing.add(result["outcome_id"])
    by_h={}
    for h in HORIZONS:
        rows=[x for x in matured if x["horizon_sessions"]==h]
        by_h[str(h)]={
          "n":len(rows),
          "avg_return_pct":(sum(x["underlying_return_pct"] for x in rows)/len(rows) if rows else None),
          "avg_mae_pct":(sum(x["mae_pct"] for x in rows)/len(rows) if rows else None),
          "avg_mfe_pct":(sum(x["mfe_pct"] for x in rows)/len(rows) if rows else None),
        }
    out={
      "version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "status":"learning_active" if matured else "waiting_for_mature_outcomes",
      "counts":{"observations":len(read_all(OBS)),"observations_added":added_obs,"matured":len(matured),"outcomes_added":added_out},
      "horizons":by_h,
      "guardrails":[
        "Measures underlying follow-through after research triage; it does not fabricate option-chain PnL.",
        "Every candidate/reject/no-trade context may be retained; absence of a trade is still an observation.",
        "Research-only. No order, sizing, option management, or Production threshold mutation."
      ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False))
