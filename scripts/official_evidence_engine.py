#!/usr/bin/env python3
"""MyAlpha V6.3 Official Evidence Layer.

Low-volume SEC EDGAR collector for symbols selected by the autonomous research
planner. Uses official SEC JSON endpoints, caches filing metadata and short
evidence excerpts, and fails soft when SEC is unavailable.

This engine is research-only. It does not place orders or change production
trading rules.
"""
from __future__ import annotations

import html, json, os, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLANNER=ROOT/"docs/research/research_planner.json"
PREVIOUS=ROOT/"docs/research/official_evidence.json"
OUT=PREVIOUS
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS="https://data.sec.gov/submissions/CIK{cik:010d}.json"
FORMS={"10-K","10-Q","8-K","6-K","20-F","40-F"}
ETF_OR_INDEX={"QQQ","QQQM","VOO","SPY","VGT","QLD","TQQQ","SMH","IBIT","GLD","RSP"}

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def request_json(url,user_agent):
    req=urllib.request.Request(url,headers={
        "User-Agent":user_agent,
        "Accept-Encoding":"identity",
        "Accept":"application/json,text/plain,*/*",
    })
    with urllib.request.urlopen(req,timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def request_text(url,user_agent):
    req=urllib.request.Request(url,headers={
        "User-Agent":user_agent,
        "Accept-Encoding":"identity",
        "Accept":"text/html,text/plain,*/*",
    })
    with urllib.request.urlopen(req,timeout=15) as r:
        return r.read().decode("utf-8",errors="ignore")

def clean_html(text):
    text=re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>"," ",text or "")
    text=re.sub(r"(?s)<[^>]+>"," ",text)
    text=html.unescape(text)
    text=re.sub(r"\s+"," ",text).strip()
    return text

def excerpts(text):
    t=clean_html(text)
    if not t:return []
    keys=[
      "Item 1.01","Item 2.02","Item 5.02","Item 7.01","Item 8.01",
      "Risk Factors","Management's Discussion","Results of Operations",
      "Liquidity and Capital Resources",
    ]
    rows=[]
    low=t.lower()
    for key in keys:
        i=low.find(key.lower())
        if i>=0:
            start=max(0,i-120); end=min(len(t),i+700)
            snippet=t[start:end].strip()
            if snippet and snippet not in rows: rows.append(snippet)
        if len(rows)>=3:break
    if not rows:rows=[t[:900]]
    return rows[:3]

def selected_symbols(planner):
    out=[]
    for row in (planner.get("today") or [])+(planner.get("queue") or []):
        if row.get("kind") not in {"market_anomaly","discovery","failure_review"}:continue
        sym=str(row.get("key") or "").upper().strip()
        if not re.fullmatch(r"[A-Z]{1,5}",sym):continue
        if sym in ETF_OR_INDEX:continue
        if sym not in out:out.append(sym)
        if len(out)>=6:break
    return out

def ticker_map(payload):
    out={}
    rows=payload.values() if isinstance(payload,dict) else payload or []
    for row in rows:
        if not isinstance(row,dict):continue
        sym=str(row.get("ticker") or "").upper()
        cik=row.get("cik_str")
        if sym and cik is not None:out[sym]={"cik":int(cik),"title":row.get("title")}
    return out

def recent_filings(submissions,cik,user_agent):
    recent=((submissions.get("filings") or {}).get("recent") or {})
    forms=recent.get("form") or []
    rows=[]
    n=min(len(forms),len(recent.get("accessionNumber") or []))
    for i in range(n):
        form=forms[i]
        if form not in FORMS:continue
        accession=(recent.get("accessionNumber") or [])[i]
        primary=(recent.get("primaryDocument") or [""]*n)[i]
        filing_date=(recent.get("filingDate") or [""]*n)[i]
        report_date=(recent.get("reportDate") or [""]*n)[i]
        acc_clean=str(accession).replace("-","")
        url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{primary}" if accession and primary else None
        row={"form":form,"accession":accession,"filing_date":filing_date,"report_date":report_date,"primary_document":primary,"url":url}
        if url:
            try:
                time.sleep(0.12)
                row["excerpts"]=excerpts(request_text(url,user_agent))
                row["document_status"]="ok"
            except Exception as exc:
                row["excerpts"]=[]
                row["document_status"]="error"
                row["document_error"]=str(exc)[:160]
        rows.append(row)
        if len(rows)>=3:break
    return rows

def build(planner,previous,user_agent):
    syms=selected_symbols(planner)
    result={"version":"6.3.0","generated_at":datetime.now(timezone.utc).isoformat(),
            "source":"SEC EDGAR official","symbols":{},"selected_symbols":syms,
            "policy":{"max_symbols":6,"max_filings_per_symbol":3,"automatic_orders":False,
                      "production_rule_mutation":False,"fail_soft":True}}
    try:
        tickers=ticker_map(request_json(SEC_TICKERS,user_agent))
        result["ticker_directory_status"]="ok"
    except Exception as exc:
        tickers={}
        result["ticker_directory_status"]="error"
        result["ticker_directory_error"]=str(exc)[:180]
    prev=(previous.get("symbols") or {}) if isinstance(previous,dict) else {}
    for sym in syms:
        meta=tickers.get(sym)
        if not meta:
            result["symbols"][sym]={"status":"unmapped","filings":[]}
            continue
        cik=meta["cik"]
        try:
            time.sleep(0.12)
            sub=request_json(SEC_SUBMISSIONS.format(cik=cik),user_agent)
            rows=recent_filings(sub,cik,user_agent)
            result["symbols"][sym]={
              "status":"ok","cik":cik,"company_name":meta.get("title") or sub.get("name"),
              "filings":rows,"fetched_at":datetime.now(timezone.utc).isoformat()
            }
        except Exception as exc:
            old=prev.get(sym) or {}
            if old:
                result["symbols"][sym]={**old,"status":"stale_cache","refresh_error":str(exc)[:180]}
            else:
                result["symbols"][sym]={"status":"error","cik":cik,"filings":[],"error":str(exc)[:180]}
    counts={
      "selected":len(syms),
      "mapped":sum(1 for x in result["symbols"].values() if x.get("cik")),
      "ok":sum(1 for x in result["symbols"].values() if x.get("status")=="ok"),
      "filings":sum(len(x.get("filings") or []) for x in result["symbols"].values()),
      "with_excerpts":sum(1 for x in result["symbols"].values() for f in x.get("filings") or [] if f.get("excerpts")),
    }
    result["counts"]=counts
    return result

def main():
    planner=load(PLANNER); previous=load(PREVIOUS)
    ua=os.getenv("SEC_USER_AGENT","MyAlphaView/6.3 research-agent myalphaview.com")
    out=build(planner,previous,ua)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
