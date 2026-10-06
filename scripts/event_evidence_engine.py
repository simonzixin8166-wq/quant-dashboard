#!/usr/bin/env python3
"""MyAlpha V6.4 Event Evidence Layer.

Free, low-volume company/market news + peer context for symbols already selected
by V6. Reuses Yahoo Finance's public search endpoint pattern already used by the
IREN daily brief. It does NOT crawl the whole market.

Output is research evidence only. Headlines/publishers are preserved with source
quality labels; no article body is fabricated when unavailable.
"""
from __future__ import annotations
import json, math, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLANNER=ROOT/"docs/research/research_planner.json"
DATA=ROOT/"docs/data.json"
PREV=ROOT/"docs/research/event_evidence.json"
OUT=PREV
SEARCH="https://query1.finance.yahoo.com/v1/finance/search?{query}"
ETF_OR_INDEX={"QQQ","QQQM","VOO","SPY","VGT","QLD","TQQQ","SMH","IBIT","GLD","RSP"}
PINNED_PUBLIC_RESEARCH=("IREN","SOFI")

PEERS={
 "MSFT":["GOOGL","AMZN","META","ORCL"],
 "LITE":["COHR","CIEN","AVGO","MRVL"],
 "AVGO":["NVDA","MRVL","QCOM","AMD"],
 "NOW":["CRM","ORCL","MSFT"],
 "NBIS":["CRWV","IREN","NVDA"],
 "CRWV":["NBIS","IREN","NVDA"],
 "IREN":["NBIS","CRWV","CORZ"],
 "NVDA":["AMD","AVGO","MRVL"],
 "ORCL":["MSFT","CRM","NOW"],
 "TSLA":["RIVN","GM","F"],
}
HIGH_QUALITY={"Reuters","Associated Press","AP Finance","Bloomberg","The Wall Street Journal","Barrons.com"}
PRESS_WIRE={"Business Wire","GlobeNewswire","PR Newswire"}
COMPANY_TERMS={
 "MSFT":["microsoft"],"LITE":["lumentum"],"AVGO":["broadcom"],"NOW":["servicenow"],
 "NBIS":["nebius"],"CRWV":["coreweave"],"IREN":["iren","iris energy"],"SOFI":["sofi","sofi technologies"],
 "NVDA":["nvidia"],"ORCL":["oracle"],"TSLA":["tesla"],
 "VGT":["vgt","vanguard information technology"],"VOO":["voo","vanguard s&p 500"],
}

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def selected_symbols(planner):
    out=list(PINNED_PUBLIC_RESEARCH)
    for row in (planner.get("today") or [])+(planner.get("queue") or []):
        if row.get("kind") not in {"market_anomaly","discovery","failure_review"}:continue
        sym=str(row.get("key") or "").upper().strip()
        if not re.fullmatch(r"[A-Z]{1,5}",sym):continue
        if sym not in out:out.append(sym)
        if len(out)>=8:break
    return out

def request_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MyAlphaView/6.4","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))

def source_class(publisher,title):
    p=str(publisher or "").strip()
    t=str(title or "").lower()
    if p in HIGH_QUALITY or "reuters" in p.lower() or "associated press" in p.lower():
        return "newswire",1
    if p in PRESS_WIRE or any(x in p.lower() for x in ("business wire","globenewswire","pr newswire")):
        return "press_release_wire",1
    if any(x in t for x in ("opinion","why i","could soar","top stock","buy now","prediction")):
        return "opinion",4
    return "media",2

def relevant_to_symbol(row,symbol):
    if not symbol:return True
    sym=str(symbol).upper()
    related={str(x).upper() for x in (row.get("relatedTickers") or [])}
    if related:return sym in related
    title=str(row.get("title") or "").lower()
    if re.search(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", title.upper()):return True
    return any(term in title for term in COMPANY_TERMS.get(sym,[]))

def normalize_news(payload,limit=5,symbol=None):
    rows=[]
    for x in payload.get("news") or []:
        title=str(x.get("title") or "").strip()
        if not title or not relevant_to_symbol(x,symbol):continue
        publisher=str(x.get("publisher") or "").strip()
        st,priority=source_class(publisher,title)
        ts=x.get("providerPublishTime")
        published=None
        try:published=datetime.fromtimestamp(int(ts),timezone.utc).isoformat()
        except Exception:pass
        link=x.get("link") or x.get("clickThroughUrl",{}).get("url")
        rows.append({
          "title":title,"publisher":publisher,"source_type":st,"source_priority":priority,
          "published_at":published,"url":link,"uuid":x.get("uuid"),
          "related_tickers":x.get("relatedTickers") or [],
        })
        if len(rows)>=limit:break
    return rows

def fetch_news(symbol,limit=5):
    q=urllib.parse.urlencode({"q":symbol,"quotesCount":1,"newsCount":max(limit*2,10)})
    return normalize_news(request_json(SEARCH.format(query=q)),limit,symbol)

def num(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def universe(data):
    u={}
    for k in ("stocks","core","index"):
        for sym,row in (data.get(k) or {}).items():
            if isinstance(row,dict):u[sym]=row
    return u

def peer_context(symbol,data):
    u=universe(data); rows=[]
    for peer in PEERS.get(symbol,[]):
        row=u.get(peer)
        if not row:continue
        chg=num(row.get("day_chg"))
        rows.append({"symbol":peer,"day_change":chg,"date":row.get("date")})
    vals=[x["day_change"] for x in rows if x["day_change"] is not None]
    if not vals:return {"peers":rows,"peer_count":len(rows),"direction":"unknown","avg_day_change":None}
    avg=sum(vals)/len(vals)
    positive=sum(x>0 for x in vals)
    negative=sum(x<0 for x in vals)
    direction="broad_positive" if positive>=max(2,len(vals)*0.67) else "broad_negative" if negative>=max(2,len(vals)*0.67) else "mixed"
    return {"peers":rows,"peer_count":len(rows),"direction":direction,"avg_day_change":avg}

def build(planner,data,previous):
    syms=selected_symbols(planner)
    prev=(previous.get("symbols") or {}) if isinstance(previous,dict) else {}
    symbols={}
    for sym in syms:
        try:
            time.sleep(0.08)
            news=fetch_news(sym,5)
            status="ok"
        except Exception as exc:
            old=prev.get(sym) or {}
            if old:
                symbols[sym]={**old,"status":"stale_cache","refresh_error":str(exc)[:160]}
                continue
            news=[];status="error"
            err=str(exc)[:160]
        row={"status":status,"news":news,"peer_context":peer_context(sym,data),"fetched_at":datetime.now(timezone.utc).isoformat()}
        if status=="error":row["error"]=err
        symbols[sym]=row
    return {
      "version":"6.4.1","generated_at":datetime.now(timezone.utc).isoformat(),
      "source":"Yahoo Finance Search + internal peer quotes","selected_symbols":syms,"symbols":symbols,
      "counts":{
        "selected":len(syms),
        "ok":sum(x.get("status")=="ok" for x in symbols.values()),
        "news_items":sum(len(x.get("news") or []) for x in symbols.values()),
        "relevance_filtered":True,
        "newswire_or_press":sum(1 for x in symbols.values() for n in x.get("news") or [] if n.get("source_priority")==1),
        "with_peer_context":sum((x.get("peer_context") or {}).get("peer_count",0)>0 for x in symbols.values()),
      },
      "policy":{
        "max_symbols":8,"max_news_per_symbol":5,
        "full_market_crawl":False,"article_body_invented":False,
        "automatic_orders":False,"production_rule_mutation":False,
        "source_hierarchy":"official SEC remains above news; newswire/press wire above general media/opinion",
      }
    }

def main():
    out=build(load(PLANNER),load(DATA),load(PREV))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
