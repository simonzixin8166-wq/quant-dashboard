#!/usr/bin/env python3
"""Point-in-time SEC CompanyFacts fundamental outcome memory.

Builds filing-event snapshots from the append-only CompanyFacts archive and
evaluates future underlying returns only after the filing date. Research-only.
"""
from __future__ import annotations
import json,sys,hashlib
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ARCH=ROOT/"research"/"archive"/"fundamentals"
OBS=ROOT/"research"/"archive"/"fundamental_observations.jsonl"
OUTCOMES=ROOT/"research"/"archive"/"fundamental_outcomes.jsonl"
OUT=ROOT/"docs"/"research"/"company_fundamental_outcome_memory.json"
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive

FLOW_METRICS={"revenue","gross_profit","operating_income","net_income","operating_cash_flow","capex","sbc"}
STOCK_METRICS={"cash","debt_current","debt_noncurrent","shares_outstanding"}
HORIZONS=(20,60)

def read_jsonl(path):
    rows=[]
    if not Path(path).exists(): return rows
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        try: rows.append(json.loads(line))
        except Exception: pass
    return rows

def append_unique(path,rows,key):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    known={str(x.get(key)) for x in read_jsonl(path)}
    added=0
    with path.open("a",encoding="utf-8") as f:
        for row in rows:
            k=str(row.get(key) or "")
            if not k or k in known:continue
            f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
            known.add(k);added+=1
    return added

def archive_rows():
    out=[]
    if not ARCH.exists():return out
    for p in ARCH.glob("*.jsonl"):
        out.extend(read_jsonl(p))
    return out

def comparable_prior(rows,current):
    metric=current.get("metric"); end=current.get("end"); start=current.get("start")
    if metric not in FLOW_METRICS or not end:return None
    try:
        end_dt=pd.Timestamp(end);start_dt=pd.Timestamp(start) if start else None
    except Exception:return None
    dur=(end_dt-start_dt).days if start_dt is not None else None
    candidates=[]
    for r in rows:
        if r is current or r.get("metric")!=metric:continue
        if str(r.get("filed") or "")>str(current.get("filed") or ""):continue
        try:
            re=pd.Timestamp(r.get("end")); rs=pd.Timestamp(r.get("start")) if r.get("start") else None
        except Exception:continue
        if abs((end_dt-re).days-365)>45:continue
        if dur is not None and rs is not None and abs((re-rs).days-dur)>20:continue
        candidates.append(r)
    return max(candidates,key=lambda x:(str(x.get("filed") or ""),str(x.get("end") or "")),default=None)

def build_observations():
    rows=archive_rows()
    by_symbol=defaultdict(list)
    for r in rows: by_symbol[str(r.get("symbol") or "")].append(r)
    observations=[]
    for symbol,srows in by_symbol.items():
        events=defaultdict(list)
        for r in srows:
            if not r.get("accn") or not r.get("filed"):continue
            events[(str(r["filed"]),str(r["accn"]),str(r.get("form") or ""))].append(r)
        for (filed,accn,form),facts in events.items():
            # One point-in-time value per metric for this filing event.
            metric_rows={}
            for r in facts:
                m=r.get("metric")
                cur=metric_rows.get(m)
                if cur is None or str(r.get("end") or "")>str(cur.get("end") or ""):
                    metric_rows[m]=r
            metrics={}
            for m,r in metric_rows.items():
                item={"value":r.get("value"),"unit":r.get("unit"),"end":r.get("end"),"start":r.get("start"),"concept":r.get("concept")}
                prior=comparable_prior(srows,r)
                if prior and prior.get("value") not in (None,0):
                    try:item["yoy_pct"]=(float(r["value"])/float(prior["value"])-1.0)*100
                    except Exception:pass
                metrics[m]=item
            if not metrics:continue
            # Derived ratios only when same-filing comparable values exist.
            rev=(metrics.get("revenue") or {}).get("value")
            gp=(metrics.get("gross_profit") or {}).get("value")
            oi=(metrics.get("operating_income") or {}).get("value")
            ni=(metrics.get("net_income") or {}).get("value")
            derived={}
            try:
                if rev:
                    if gp is not None:derived["gross_margin_pct"]=float(gp)/float(rev)*100
                    if oi is not None:derived["operating_margin_pct"]=float(oi)/float(rev)*100
                    if ni is not None:derived["net_margin_pct"]=float(ni)/float(rev)*100
            except Exception:pass
            raw=f"{symbol}|{filed}|{accn}|{form}"
            observations.append({
                "observation_id":hashlib.sha256(raw.encode()).hexdigest()[:24],
                "symbol":symbol,"filed":filed,"accn":accn,"form":form,
                "metrics":metrics,"derived":derived,
                "source":"SEC CompanyFacts point-in-time archive",
                "production_effect":"none"
            })
    observations.sort(key=lambda x:(x["filed"],x["symbol"],x["accn"]))
    return observations

def mature(obs,df,h):
    if df is None or df.empty:return None
    try:day=pd.Timestamp(obs["filed"])
    except Exception:return None
    # First tradable close strictly after filing date: conservative, avoids
    # assuming filing-time knowledge during the filing day's session.
    fut=df[df.index>day].sort_index().head(h)
    if len(fut)<h:return None
    start=float(fut["close"].iloc[0]); end=float(fut["close"].iloc[-1])
    low=float(fut["low"].min()); high=float(fut["high"].max())
    return {
        "outcome_id":f"{obs['observation_id']}:{h}",
        "observation_id":obs["observation_id"],"symbol":obs["symbol"],
        "filed":obs["filed"],"horizon_sessions":h,"horizon_end":str(fut.index[-1])[:10],
        "return_pct":(end/start-1)*100,
        "mae_pct":(low/start-1)*100,
        "mfe_pct":(high/start-1)*100,
        "matured_at":datetime.now(timezone.utc).isoformat(),
        "production_effect":"none"
    }

def run(histories=None):
    histories=histories if histories is not None else read_archive()
    observations=build_observations()
    added_obs=append_unique(OBS,observations,"observation_id")
    all_obs=read_jsonl(OBS)
    matured=[]
    for obs in all_obs:
        for h in HORIZONS:
            x=mature(obs,histories.get(obs.get("symbol")),h)
            if x:matured.append(x)
    added_out=append_unique(OUTCOMES,matured,"outcome_id")
    all_out=read_jsonl(OUTCOMES)
    score={}
    for h in HORIZONS:
        rows=[x for x in all_out if int(x.get("horizon_sessions") or 0)==h]
        score[str(h)]={
          "n":len(rows),
          "avg_return_pct":sum(float(x["return_pct"]) for x in rows)/len(rows) if rows else None,
          "positive_rate":sum(float(x["return_pct"])>0 for x in rows)/len(rows) if rows else None,
          "avg_mae_pct":sum(float(x["mae_pct"]) for x in rows)/len(rows) if rows else None,
          "avg_mfe_pct":sum(float(x["mfe_pct"]) for x in rows)/len(rows) if rows else None,
        }
    out={
      "version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "status":"learning_active" if all_out else "waiting_for_mature_outcomes",
      "counts":{"observations":len(all_obs),"observations_added":added_obs,"outcomes":len(all_out),"outcomes_added":added_out},
      "horizons":score,
      "guardrails":[
        "All financial facts retain SEC filed-date availability; no later filing is allowed into an earlier observation.",
        "Future-price evaluation starts strictly after filing date to avoid filing-time look-ahead.",
        "This evaluates fundamental evidence/outcomes only and cannot mutate Production rules."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False))
