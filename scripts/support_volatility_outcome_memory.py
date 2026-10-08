#!/usr/bin/env python3
"""Outcome memory for Support/Resistance and GARCH research context.

Freezes dated observations, then matures 20-session outcomes from canonical
STOOQ history. Research-only: no trading action or Production-rule mutation.
"""
from __future__ import annotations
import hashlib,json,math,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CURRENT=ROOT/"docs"/"research"/"support_volatility_intelligence.json"
OBS_DIR=ROOT/"research"/"archive"/"support_volatility_observations"
OUTCOME_DIR=ROOT/"research"/"archive"/"support_volatility_outcomes"
OUT=ROOT/"docs"/"research"/"support_volatility_outcome_memory.json"
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive

HORIZON=20

def load(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def stable_id(symbol,as_of):
    return hashlib.sha256(f"{symbol}|{as_of}|support_volatility_v1".encode()).hexdigest()[:24]

def append_jsonl(path,row,key):
    path.parent.mkdir(parents=True,exist_ok=True)
    known=set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:known.add(str(json.loads(line).get(key)))
            except Exception:continue
    if str(row.get(key)) in known:return False
    with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    return True

def snapshot_rows(current):
    out=[]
    for symbol,node in (current.get("records") or {}).items():
        if node.get("status")!="ok" or not node.get("as_of"):continue
        sr=node.get("support_resistance") or {};vol=node.get("volatility") or {};g=vol.get("garch20") or {}
        out.append({
          "observation_id":stable_id(symbol,node.get("as_of")),"symbol":symbol,"as_of":node.get("as_of"),
          "observed_at":current.get("generated_at"),"spot":sr.get("current_price"),
          "nearest_support":sr.get("nearest_support"),"nearest_resistance":sr.get("nearest_resistance"),
          "rv20_ann_pct":vol.get("rv20_ann_pct"),"rv60_ann_pct":vol.get("rv60_ann_pct"),
          "garch20_ann_vol_pct":g.get("ann_vol_pct_avg") if g.get("status")=="ok" else None,
          "garch_status":g.get("status"),"horizon_sessions":HORIZON,
          "production_effect":"none",
        })
    return out

def all_observations():
    rows=[]
    if not OBS_DIR.exists():return rows
    for p in OBS_DIR.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:rows.append(json.loads(line))
            except Exception:pass
    return rows

def mature(obs,df):
    if df is None or df.empty:return None
    try:day=pd.Timestamp(str(obs["as_of"])[:10])
    except Exception:return None
    future=df[df.index>day].sort_index().head(HORIZON+1)
    # 20 realized close-to-close returns require 21 future closes.
    if len(future)<HORIZON+1:return None
    closes=future["close"].astype(float)
    highs=future["high"].astype(float);lows=future["low"].astype(float)
    rets=np.log(closes/closes.shift(1)).dropna()
    realized=float(rets.std(ddof=1)*math.sqrt(252)*100) if len(rets)>=2 else None
    support=obs.get("nearest_support") or {}
    s_low=support.get("low");s_high=support.get("high")
    touched=broken=bounced=None
    if s_low is not None and s_high is not None:
        mask=(lows<=float(s_high)) & (highs>=float(s_low))
        touched=bool(mask.any())
        broken=bool((closes<float(s_low)).any())
        if touched:
            first=int(np.argmax(mask.to_numpy()))
            touch_ref=float(s_high) if float(s_high)>0 else None
            post_high=float(highs.iloc[first:].max())
            bounced=(post_high/touch_ref-1.0) if touch_ref else None
    pred=obs.get("garch20_ann_vol_pct")
    return {
      "outcome_id":f"{obs['observation_id']}:20","observation_id":obs["observation_id"],
      "symbol":obs["symbol"],"as_of":obs["as_of"],"horizon_sessions":20,
      "horizon_end":str(future.index[HORIZON])[:10],
      "future_return_pct":float(closes.iloc[-1]/float(obs["spot"])-1.0)*100 if obs.get("spot") else None,
      "mae_pct":float(lows.min()/float(obs["spot"])-1.0)*100 if obs.get("spot") else None,
      "mfe_pct":float(highs.max()/float(obs["spot"])-1.0)*100 if obs.get("spot") else None,
      "support_touched":touched,"support_broken":broken,
      "support_bounce_from_zone_high_pct":None if bounced is None else bounced*100,
      "garch20_forecast_ann_pct":pred,"realized_next20_ann_pct":realized,
      "garch_error_pct_points":None if pred is None or realized is None else realized-float(pred),
      "matured_at":datetime.now(timezone.utc).isoformat(),"production_effect":"none",
    }

def outcome_ids():
    ids=set()
    if not OUTCOME_DIR.exists():return ids
    for p in OUTCOME_DIR.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:ids.add(str(json.loads(line).get("outcome_id")))
            except Exception:pass
    return ids

def run(current=None,histories=None):
    current=current or load(CURRENT,{})
    histories=histories if histories is not None else read_archive()
    added_obs=0
    for row in snapshot_rows(current):
        p=OBS_DIR/f"{str(row['as_of'])[:7]}.jsonl"
        added_obs+=int(append_jsonl(p,row,"observation_id"))
    existing=outcome_ids();added_out=0;outcomes=[]
    for obs in all_observations():
        oid=f"{obs.get('observation_id')}:20"
        result=mature(obs,histories.get(obs.get("symbol")))
        if result:
            if oid not in existing:
                p=OUTCOME_DIR/f"{str(result['horizon_end'])[:7]}.jsonl"
                if append_jsonl(p,result,"outcome_id"):
                    added_out+=1;existing.add(oid)
            outcomes.append(result)
    errs=[x["garch_error_pct_points"] for x in outcomes if x.get("garch_error_pct_points") is not None]
    touched=[x for x in outcomes if x.get("support_touched") is not None]
    summary={
      "version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "status":"learning_active" if outcomes else "waiting_for_mature_outcomes",
      "counts":{"observations":len(all_observations()),"observations_added":added_obs,"mature20":len(outcomes),"outcomes_added":added_out},
      "metrics":{
        "garch_mae_pct_points":(sum(abs(x) for x in errs)/len(errs) if errs else None),
        "garch_bias_pct_points":(sum(errs)/len(errs) if errs else None),
        "support_touch_n":sum(1 for x in touched if x.get("support_touched")),
        "support_break_n":sum(1 for x in touched if x.get("support_broken")),
      },
      "guardrails":["20D maturity uses future canonical STOOQ sessions only after observation date.","Outcome memory is research-only and cannot create orders or mutate Production thresholds."]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

def main():
    print(json.dumps(run(),ensure_ascii=False))

if __name__=="__main__":main()
