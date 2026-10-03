#!/usr/bin/env python3
"""MyAlpha V6.8 Breadth Intelligence + Regime Combination Memory.

Adds participation quality beyond headline index levels:
- 20/50/200-day breadth
- S&P 500 advance/decline pressure
- 52-week high/low participation
- equal-weight relative strength (RSP/SPY, QQQE/QQQ)
- auditable regime fingerprints with 5/20/60-session outcomes, MAE and MFE

Research-only. It never changes production allocation rules or places orders.
"""
from __future__ import annotations

import json, math, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
DASH=ROOT/"docs/data.json"
CROSS=ROOT/"docs/research/cross_asset_divergence.json"
OUT=ROOT/"docs/research/breadth_intelligence.json"
HISTORY=ROOT/"docs/research/breadth_intelligence_history.json"
HEADERS={"User-Agent":"Mozilla/5.0 MyAlphaView/6.8"}

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def _completed_us_date(now_utc=None):
    now=now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None: now=now.replace(tzinfo=timezone.utc)
    ny=now.astimezone(ZoneInfo("America/New_York"))
    d=ny.date()
    if ny.weekday()<5 and (ny.hour,ny.minute)<(16,10):
        from datetime import timedelta
        d-=timedelta(days=1)
    from datetime import timedelta
    while d.weekday()>=5:d-=timedelta(days=1)
    return d.isoformat()

def yahoo_close(symbol, range_="1y"):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_}"
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=20) as r:
        payload=json.loads(r.read().decode("utf-8"))
    result=payload["chart"]["result"][0]
    ts=result.get("timestamp") or []
    closes=((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out=[]
    cutoff=_completed_us_date()
    for t,c in zip(ts,closes):
        if c is None:continue
        d=datetime.fromtimestamp(int(t),timezone.utc).date().isoformat()
        if d<=cutoff:out.append({"d":d,"c":float(c)})
    return out

def relative_pair(left_rows,right_rows,left,right):
    a={str(x.get("d")):num(x.get("c")) for x in left_rows}
    b={str(x.get("d")):num(x.get("c")) for x in right_rows}
    dates=sorted(d for d in set(a)&set(b) if a[d] and b[d])
    ratios=[(d,a[d]/b[d]) for d in dates]
    if len(ratios)<21:
        return {"available":False,"pair":f"{left}/{right}","unknown":"有效重叠日不足21日"}
    latest=ratios[-1][1]
    chg20=latest/ratios[-21][1]-1
    chg60=latest/ratios[-61][1]-1 if len(ratios)>=61 else None
    ma50=sum(x[1] for x in ratios[-50:])/min(50,len(ratios))
    return {
      "available":True,"pair":f"{left}/{right}","date":ratios[-1][0],
      "ratio":latest,"chg20":chg20,"chg60":chg60,
      "vs_ma50":latest/ma50-1 if ma50 else None,
      "signal":"weak" if chg20<=-0.01 else "strong" if chg20>=0.01 else "neutral",
    }

def cross_hits(cross):
    return {x.get("key"):x for x in (cross.get("signals") or [])}

def build(dash,cross,relative=None,history=None):
    relative=relative or {}
    history=history or {}
    raw=dash.get("raw_breadth") or {}
    mkt=dash.get("market_regime") or {}
    hits=cross_hits(cross)
    b20=num(raw.get("b20"));b50=num(raw.get("b50"));b200=num(raw.get("b200"))
    ad20=num(raw.get("ad_line_20d")); ad60=num(raw.get("ad_line_60d"))
    nh=num(raw.get("new_high_52w_pct")); nl=num(raw.get("new_low_52w_pct"))
    near_high=num(raw.get("near_high_52w_pct"))
    rsp=relative.get("rsp_spy") or {}
    qeq=relative.get("qqqe_qqq") or {}

    flags={
      "EQUITY_NEAR_HIGH":bool((hits.get("equity_near_high") or {}).get("hit")),
      "RATES_UP":bool((hits.get("rates_pressure") or {}).get("hit")),
      "REAL_YIELD_UP":bool((hits.get("real_yield_pressure") or {}).get("hit")),
      "CREDIT_WIDENING":bool((hits.get("credit_widening") or {}).get("hit")),
      "VIX_LOW":bool((hits.get("vix_disconnect") or {}).get("hit")),
      "BREADTH_WEAK":bool((b20 is not None and b20<.35) or (b50 is not None and b50<.35) or (b200 is not None and b200<.50)),
      "AD_NEGATIVE":bool(ad20 is not None and ad20<0),
      "NEW_HIGHS_THIN":bool(nh is not None and nh<.10),
      "EQUAL_WEIGHT_WEAK":bool(
        (rsp.get("available") and (num(rsp.get("chg20")) or 0)<=-.01) or
        (qeq.get("available") and (num(qeq.get("chg20")) or 0)<=-.01)
      ),
    }
    active=[k for k,v in flags.items() if v]
    combo="+".join(active) if active else "NO_MAJOR_DIVERGENCE"

    participation_risks=sum(flags[k] for k in ("BREADTH_WEAK","AD_NEGATIVE","NEW_HIGHS_THIN","EQUAL_WEIGHT_WEAK"))
    if flags["EQUITY_NEAR_HIGH"] and participation_risks>=3:
        level,label="high","高位参与度收缩"
    elif flags["EQUITY_NEAR_HIGH"] and participation_risks>=2:
        level,label="medium","中度参与度背离"
    elif participation_risks>=2:
        level,label="watch","市场参与度偏弱"
    else:
        level,label="normal","市场参与度正常/证据有限"

    unknowns=[]
    if ad20 is None:unknowns.append("A/D 20日累计尚未形成稳定样本")
    if nh is None:unknowns.append("52周新高参与率尚未形成稳定样本")
    if not rsp.get("available"):unknowns.append("RSP/SPY 等权相对强度暂不可用")
    if not qeq.get("available"):unknowns.append("QQQE/QQQ 等权相对强度暂不可用")

    records=history.get("records") or []
    same=[r for r in records if r.get("fingerprint")==combo]
    stats={}
    for h in ("5","20","60"):
        vals=[((r.get("outcomes") or {}).get(h) or {}) for r in same]
        vals=[x for x in vals if isinstance(x.get("return"),(int,float))]
        if vals:
            rets=[x["return"] for x in vals]
            maes=[x.get("mae") for x in vals if isinstance(x.get("mae"),(int,float))]
            mfes=[x.get("mfe") for x in vals if isinstance(x.get("mfe"),(int,float))]
            stats[h]={
              "n":len(rets),"avg_return":sum(rets)/len(rets),
              "win_rate":sum(x>0 for x in rets)/len(rets),
              "avg_mae":sum(maes)/len(maes) if maes else None,
              "avg_mfe":sum(mfes)/len(mfes) if mfes else None,
            }
        else:stats[h]={"n":0}

    return {
      "version":"6.8.0","generated_at":datetime.now(timezone.utc).isoformat(),
      "as_of":str(dash.get("spy_date") or dash.get("updated") or "")[:10],
      "level":level,"label":label,"participation_risks":participation_risks,
      "breadth":{
        "date":raw.get("date"),"coverage":raw.get("coverage"),"universe":raw.get("universe"),
        "b20":b20,"b50":b50,"b200":b200,"slope_10d":num(raw.get("slope_10d")),
        "advance_pct":num(raw.get("advance_pct")),"decline_pct":num(raw.get("decline_pct")),
        "ad_net_pct":num(raw.get("ad_net_pct")),"ad_line_20d":ad20,"ad_line_60d":ad60,
        "new_high_52w_pct":nh,"near_high_52w_pct":near_high,"new_low_52w_pct":nl,
      },
      "equal_weight":relative,
      "flags":flags,"fingerprint":combo,
      "current_combination_history":stats,
      "unknowns":unknowns,
      "next_validation":[
        "RSP/SPY 与 QQQE/QQQ 是否继续弱于市值加权指数",
        "A/D累计线是否继续恶化或出现修复",
        "52周新高参与率是否扩散",
        "当前组合状态5/20/60日样本如何成熟",
      ],
      "guardrail":"Breadth Intelligence 是市场参与度与风险环境研究层，不是卖出、做空或自动调仓信号。",
    }

def mature_history(history,spy_rows):
    records=list((history or {}).get("records") or [])
    prices={str(x.get("d")):num(x.get("c")) for x in spy_rows if x.get("d")}
    dates=sorted(d for d,v in prices.items() if v is not None)
    pos={d:i for i,d in enumerate(dates)}
    for row in records:
        d=str(row.get("as_of") or ""); anchor=num(row.get("anchor_spy"))
        if d not in pos or anchor is None:continue
        i=pos[d]; outcomes=row.setdefault("outcomes",{})
        for h in (5,20,60):
            j=i+h
            if str(h) in outcomes or j>=len(dates):continue
            path=[prices[dates[k]] for k in range(i+1,j+1) if prices[dates[k]] is not None]
            if not path:continue
            end=path[-1]
            outcomes[str(h)]={
              "date":dates[j],"return":end/anchor-1,
              "mae":min(path)/anchor-1,"mfe":max(path)/anchor-1,
            }
    return {"version":"6.8.0","records":records[-500:]}

def main():
    dash=load(DASH);cross=load(CROSS)
    relative={}
    for key,left,right in (("rsp_spy","RSP","SPY"),("qqqe_qqq","QQQE","QQQ")):
        try:relative[key]=relative_pair(yahoo_close(left,"1y"),yahoo_close(right,"1y"),left,right)
        except Exception as e:relative[key]={"available":False,"pair":f"{left}/{right}","unknown":str(e)[:180]}
    try:spy=yahoo_close("SPY","2y")
    except Exception:spy=((dash.get("overview_charts") or {}).get("SPY") or [])
    history=mature_history(load(HISTORY),spy)
    out=build(dash,cross,relative,history)
    as_of=out.get("as_of")
    anchor=num(((dash.get("index") or {}).get("SPY") or {}).get("close"))
    if as_of and anchor is not None:
        rows=history.setdefault("records",[])
        snap={
          "as_of":as_of,"anchor_spy":anchor,"level":out["level"],"label":out["label"],
          "fingerprint":out["fingerprint"],"flags":out["flags"],
          "breadth":out["breadth"],"equal_weight":out["equal_weight"],"outcomes":{}
        }
        old=next((x for x in rows if x.get("as_of")==as_of),None)
        if old:
            snap["outcomes"]=old.get("outcomes") or {}
            rows[rows.index(old)]=snap
        else:rows.append(snap)
        history["records"]=rows[-500:]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":out["version"],"level":out["level"],"fingerprint":out["fingerprint"],"history":len(history.get("records") or [])},ensure_ascii=False))

if __name__=="__main__":main()
