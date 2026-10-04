#!/usr/bin/env python3
"""V6.11 Walk-Forward Replay Engine (research-only).

Replays only production-rule components that can be causally reconstructed from
the local STOOQ archive. Historical replay is always labeled
historical_replay_post_rule_design and is never mixed with Forward evidence.

Current coverage:
- CP-01: full replay for QQQM / VGT / QLD from validated historical OHLCV.
- CP-02: coverage blocked until VIX history is present; QQQ-only approximation is
  intentionally rejected.
- CP-03: partial replay is intentionally withheld from aggregate scoring until
  SMH + VIX/risk dependencies are available. No LEAPS P&L is inferred.

The engine reports raw/effective sample counts, clustered independent dates,
5/20/60-session outcomes, MAE/MFE, QQQ excess return, and Wilson intervals.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from local_history_agent import read_archive
from playbook_config import CORE_TIERS, rule_hash

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"walk_forward_replay.json"
VERSION="6.11.0"
HORIZONS=(5,20,60)
CLUSTER_SESSIONS=5
PROVENANCE="historical_replay_post_rule_design"

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def wilson(k,n,z=1.959963984540054):
    if not n:return {"low":None,"high":None}
    p=k/n
    den=1+z*z/n
    centre=(p+z*z/(2*n))/den
    margin=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return {"low":max(0.0,centre-margin),"high":min(1.0,centre+margin)}

def qqq_return(qqq,event_date,h):
    if qqq is None or qqq.empty:return None
    ts=pd.Timestamp(event_date)
    if ts not in qqq.index:return None
    pos=qqq.index.get_loc(ts)
    if not isinstance(pos,int) or pos+h>=len(qqq):return None
    a=finite(qqq.iloc[pos]["close"]);b=finite(qqq.iloc[pos+h]["close"])
    return None if not a or b is None else b/a-1.0

def fwd_outcomes(df,pos,entry,qqq,event_date):
    out={}
    for h in HORIZONS:
        if pos+h>=len(df):
            out[str(h)]=None
            continue
        end=finite(df.iloc[pos+h]["close"])
        if end is None or not entry:
            out[str(h)]=None
            continue
        path=df.iloc[pos+1:pos+h+1]
        lows=[finite(x) for x in path["low"].tolist()]; highs=[finite(x) for x in path["high"].tolist()]
        lows=[x for x in lows if x is not None]; highs=[x for x in highs if x is not None]
        ret=end/entry-1.0
        bench=qqq_return(qqq,event_date,h)
        out[str(h)]={
            "maturity_date":df.index[pos+h].date().isoformat(),
            "return":ret,
            "mae":min(lows)/entry-1.0 if lows else None,
            "mfe":max(highs)/entry-1.0 if highs else None,
            "benchmark_return":bench,
            "excess_vs_benchmark":ret-bench if bench is not None else None,
            "aligned":ret>0,
        }
    return out

def cp01_events(symbol,df,qqq):
    if symbol not in CORE_TIERS:return []
    tiers=CORE_TIERS[symbol]
    x=df.copy().sort_index()
    x=x[~x.index.duplicated(keep="last")]
    if len(x)<80:return []
    close=x["close"].astype(float)
    ath=close.cummax()
    dd=close/ath-1.0
    levels=np.zeros(len(x),dtype=int)
    levels=np.where(dd<=-tiers["t1"],1,levels)
    levels=np.where(dd<=-tiers["t2"],2,levels)
    levels=np.where(dd<=-tiers["t3"],3,levels)
    events=[];prev=0
    for i,level in enumerate(levels):
        level=int(level)
        if i==0:
            prev=level;continue
        if level==prev:
            continue
        # Only entries into a triggered tier are scoreable. Returns to 0 are
        # state transitions but not opportunity outcomes.
        if level>=1:
            entry=finite(close.iloc[i])
            if entry:
                day=x.index[i].date().isoformat()
                events.append({
                    "playbook_id":"CP-01",
                    "entity_key":f"CP-01:{symbol}",
                    "symbol":symbol,
                    "event_date":day,
                    "state_detail":f"tier{level}",
                    "previous_level":prev,
                    "baseline_close":entry,
                    "rule_hash":rule_hash("CP-01"),
                    "evidence_provenance":PROVENANCE,
                    "scoreable":True,
                    "outcomes":fwd_outcomes(x,i,entry,qqq,day),
                })
        prev=level
    return events

def session_distance(index,a,b):
    try:
        ia=index.get_loc(pd.Timestamp(a));ib=index.get_loc(pd.Timestamp(b))
        if isinstance(ia,int) and isinstance(ib,int):return abs(ib-ia)
    except Exception:pass
    return 10**9

def cluster_effective(events,reference_index,window=CLUSTER_SESSIONS):
    """Collapse temporally clustered signals into independent-date clusters.

    Conservative rule: within each playbook/state_detail, events across all
    symbols separated by <= window trading sessions share one cluster.
    """
    groups=defaultdict(list)
    for e in events:
        groups[(e["playbook_id"],e["state_detail"])].append(e)
    clusters=[]
    for key,rows in groups.items():
        rows=sorted(rows,key=lambda x:x["event_date"])
        current=[]
        for row in rows:
            if not current:
                current=[row];continue
            if session_distance(reference_index,current[-1]["event_date"],row["event_date"])<=window:
                current.append(row)
            else:
                clusters.append((key,current));current=[row]
        if current:clusters.append((key,current))
    return clusters

def avg(vals):
    x=[float(v) for v in vals if v is not None and math.isfinite(float(v))]
    return None if not x else sum(x)/len(x)

def median(vals):
    x=[float(v) for v in vals if v is not None and math.isfinite(float(v))]
    return None if not x else float(np.median(np.asarray(x,dtype=float)))

def summarize(events,reference_index):
    clusters=cluster_effective(events,reference_index)
    cluster_id={}
    for i,(_,rows) in enumerate(clusters,1):
        for r in rows:cluster_id[id(r)]=f"C{i:04d}"
    by_key={}
    grouped=defaultdict(list)
    for e in events:grouped[(e["playbook_id"],e["state_detail"])].append(e)
    for (pid,detail),rows in sorted(grouped.items()):
        row_clusters={cluster_id[id(r)] for r in rows}
        hs={}
        for h in HORIZONS:
            mature=[r["outcomes"][str(h)] for r in rows if r["outcomes"].get(str(h))]
            aligned=sum(1 for x in mature if x.get("aligned"))
            hs[str(h)]={
                "raw_n":len(mature),
                "effective_n":len({cluster_id[id(r)] for r in rows if r["outcomes"].get(str(h))}),
                "aligned_rate":aligned/len(mature) if mature else None,
                "aligned_rate_ci95":wilson(aligned,len(mature)),
                "avg_return":avg([x.get("return") for x in mature]),
                "median_return":median([x.get("return") for x in mature]),
                "avg_mae":avg([x.get("mae") for x in mature]),
                "avg_mfe":avg([x.get("mfe") for x in mature]),
                "avg_excess_vs_qqq":avg([x.get("excess_vs_benchmark") for x in mature]),
            }
        by_key[f"{pid}:{detail}"]={
            "playbook_id":pid,
            "state_detail":detail,
            "raw_events":len(rows),
            "effective_clusters":len(row_clusters),
            "independent_dates":[min(r["event_date"] for r in rows if cluster_id[id(r)]==cid) for cid in sorted(row_clusters)],
            "horizons":hs,
        }
    return by_key,len(clusters)

def build(store=None,now=None):
    now=now or datetime.now(timezone.utc)
    store=read_archive() if store is None else store
    qqq=store.get("QQQ")
    coverage={
        "CP-01":{
            "status":"complete" if all(x in store for x in ("QQQM","VGT","QLD","QQQ")) else "blocked",
            "required_history":["QQQM","VGT","QLD","QQQ"],
            "missing":[x for x in ("QQQM","VGT","QLD","QQQ") if x not in store],
            "replay_rule":"validated drawdown tiers reconstructed causally from cumulative adjusted close ATH",
        },
        "CP-02":{
            "status":"blocked",
            "required_history":["QQQ","VIX"],
            "missing":[x for x in ("QQQ","VIX") if x not in store],
            "reason":"VIX history is required by production hard-exit/tier/restore semantics. QQQ-only approximation is rejected.",
        },
        "CP-03":{
            "status":"blocked",
            "required_history":["QQQ","SMH","VGT","VIX"],
            "missing":[x for x in ("QQQ","SMH","VGT","VIX") if x not in store],
            "reason":"Full production LEAPS market-condition replay needs SMH plus risk-context dependency. Partial reconstruction is not promoted into aggregate evidence.",
        },
    }
    events=[]
    if coverage["CP-01"]["status"]=="complete":
        for symbol in ("QQQM","VGT","QLD"):
            events.extend(cp01_events(symbol,store[symbol],qqq))
    ref=qqq.index if qqq is not None and not qqq.empty else next(iter(store.values())).index if store else pd.DatetimeIndex([])
    stats,effective_total=summarize(events,ref)
    recent=sorted(events,key=lambda x:(x["event_date"],x["symbol"]),reverse=True)[:120]
    return {
        "version":VERSION,
        "generated_at":now.astimezone(timezone.utc).isoformat(),
        "mode":"research_only",
        "evidence_provenance":PROVENANCE,
        "forward_evidence_mixed":False,
        "automatic_promotion":False,
        "production_rule_mutation":False,
        "coverage":coverage,
        "summary":{
            "raw_events":len(events),
            "effective_clusters":effective_total,
            "replayable_playbooks":sum(1 for x in coverage.values() if x["status"]=="complete"),
            "blocked_playbooks":sum(1 for x in coverage.values() if x["status"]=="blocked"),
            "history_symbols":len(store),
        },
        "statistics":stats,
        "recent_replay_events":recent,
        "methodology":{
            "horizons":list(HORIZONS),
            "cluster_sessions":CLUSTER_SESSIONS,
            "effective_n":"signals with the same playbook/detail within <=5 QQQ trading sessions are collapsed into one cluster",
            "confidence_interval":"Wilson 95% interval on raw directional alignment rate; effective_n is displayed separately to prevent clustered events looking independent",
            "benchmark":"QQQ where available",
        },
        "guardrails":[
            "Historical replay is post-rule-design research evidence, never Forward evidence.",
            "Replay cannot write the private Forward Ledger.",
            "Blocked dependencies are not approximated to inflate sample size.",
            "No replay statistic may automatically promote a rule or change production thresholds.",
            "No option P&L is inferred from underlying returns.",
        ],
    }

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":out["version"],"summary":out["summary"],"coverage":{k:v["status"] for k,v in out["coverage"].items()}},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
