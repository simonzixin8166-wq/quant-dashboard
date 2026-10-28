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
try:  # SEC fair-access identity (secret, never persisted)
    from sec_identity import user_agent as sec_user_agent
except ModuleNotFoundError:  # loaded by file path (tests) without scripts/ on sys.path
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from sec_identity import user_agent as sec_user_agent

ROOT=Path(__file__).resolve().parents[1]
PLANNER=ROOT/"docs/research/research_planner.json"
PREVIOUS=ROOT/"docs/research/official_evidence.json"
EVIDENCE=ROOT/"docs/research/evidence_attribution.json"
OUT=PREVIOUS
ARCHIVE=ROOT/"research/archive/sec_filings"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS="https://data.sec.gov/submissions/CIK{cik:010d}.json"
FORMS={"10-K","10-Q","8-K","6-K","20-F","40-F"}
ETF_OR_INDEX={"QQQ","QQQM","VOO","SPY","VGT","QLD","TQQQ","SMH","IBIT","GLD","RSP"}
PINNED_PUBLIC_RESEARCH=("IREN","SOFI")

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

def selected_symbols(planner,evidence=None):
    out=[s for s in PINNED_PUBLIC_RESEARCH if s not in ETF_OR_INDEX]
    def add_rows(rows):
        for row in rows or []:
            if row.get("kind") not in {"market_anomaly","discovery","failure_review"}:continue
            sym=str(row.get("key") or "").upper().strip()
            if not re.fullmatch(r"[A-Z]{1,5}",sym):continue
            if sym in ETF_OR_INDEX:continue
            if sym not in out:out.append(sym)

    # Current-day research keeps priority, but mature outcome reviews come
    # before the backlog queue so failed/missed samples can obtain evidence
    # context and actually close the learning loop.
    add_rows(planner.get("today") or [])
    reviews=((evidence or {}).get("failure_attribution") or {}).get("external_outcome_reviews") or []
    # #133 P0-A: unverified author self-reports do not decide which symbols get evidence collected
    reviews=[r for r in reviews if r.get("learning_eligible") is True]
    for row in reviews:
        sym=str(row.get("symbol") or "").upper().strip()
        if not re.fullmatch(r"[A-Z]{1,5}",sym):continue
        if sym in ETF_OR_INDEX:continue
        if sym not in out:out.append(sym)
    add_rows(planner.get("queue") or [])
    return out[:14]

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

def archive_rows(root=ARCHIVE):
    """Append-only SEC filing archive (research/archive/sec_filings/*.jsonl) written by evidence_archive.py."""
    rows=[]
    for path in sorted(Path(root).glob("*.jsonl")) if Path(root).exists() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:rows.append(json.loads(line))
                except ValueError:continue
    return rows

def cached_symbol(sym,prev,archive):
    """Last known identity and filings for one symbol when SEC cannot be reached (E-17).
    Prefers the previous published file, then the append-only archive; returns None if neither knows the symbol."""
    old=prev.get(sym) or {}
    if old.get("cik") and old.get("filings"):
        return {"cik":old["cik"],"company_name":old.get("company_name"),"filings":old["filings"],"cache_source":"previous"}
    rows=[r for r in archive if str(r.get("symbol") or "").upper()==sym and r.get("cik")]
    if not rows:
        return {"cik":old["cik"],"company_name":old.get("company_name"),"filings":[],"cache_source":"previous"} if old.get("cik") else None
    rows.sort(key=lambda r:(str(r.get("filing_date") or ""),str(r.get("accession") or "")),reverse=True)
    seen,filings=set(),[]
    for r in rows:
        key=r.get("accession") or r.get("url")
        if key in seen:continue
        seen.add(key)
        filings.append({k:r.get(k) for k in ("form","accession","filing_date","report_date","primary_document","url","document_status")}|{"excerpts":r.get("excerpts") or []})
        if len(filings)>=3:break
    return {"cik":rows[0]["cik"],"company_name":rows[0].get("company_name"),"filings":filings,"cache_source":"archive"}

def build(planner,previous,user_agent,evidence=None,archive=None):
    syms=selected_symbols(planner,evidence)
    result={"version":"6.3.0","generated_at":datetime.now(timezone.utc).isoformat(),
            "source":"SEC EDGAR official","symbols":{},"selected_symbols":syms,
            "policy":{"max_symbols":14,"max_filings_per_symbol":3,"automatic_orders":False,
                      "production_rule_mutation":False,"fail_soft":True}}
    try:
        tickers=ticker_map(request_json(SEC_TICKERS,user_agent))
        result["ticker_directory_status"]="ok"
    except Exception as exc:
        tickers={}
        result["ticker_directory_status"]="error"
        result["ticker_directory_error"]=str(exc)[:180]
    prev=(previous.get("symbols") or {}) if isinstance(previous,dict) else {}
    directory_failed=result["ticker_directory_status"]!="ok"
    if directory_failed and archive is None:
        archive=archive_rows()
    for sym in syms:
        meta=tickers.get(sym)
        cached=cached_symbol(sym,prev,archive or []) if directory_failed else None
        if not meta and cached:
            # directory down: keep the last known CIK instead of declaring the symbol unmapped (E-17)
            meta={"cik":int(cached["cik"]),"title":cached.get("company_name"),"cik_source":"cache"}
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
            fallback=cached or (cached_symbol(sym,prev,archive or []) if not old.get("filings") else None)
            if old.get("filings"):
                result["symbols"][sym]={**old,"status":"stale_cache","refresh_error":str(exc)[:180]}
            elif fallback and fallback.get("filings"):
                # never replace known filings with an empty list during an outage; label them as cached
                result["symbols"][sym]={"status":"stale_cache","cik":fallback["cik"],"company_name":fallback.get("company_name"),
                                        "filings":fallback["filings"],"cache_source":fallback["cache_source"],
                                        "refresh_error":str(exc)[:180]}
            else:
                result["symbols"][sym]={"status":"error","cik":cik,"filings":[],"error":str(exc)[:180]}
    counts={
      "selected":len(syms),
      "mapped":sum(1 for x in result["symbols"].values() if x.get("cik")),
      "ok":sum(1 for x in result["symbols"].values() if x.get("status")=="ok"),
      "stale_cache":sum(1 for x in result["symbols"].values() if x.get("status")=="stale_cache"),
      "filings":sum(len(x.get("filings") or []) for x in result["symbols"].values()),
      "with_excerpts":sum(1 for x in result["symbols"].values() for f in x.get("filings") or [] if f.get("excerpts")),
    }
    result["counts"]=counts
    return result

def main():
    planner=load(PLANNER); previous=load(PREVIOUS)
    ua=sec_user_agent()
    out=build(planner,previous,ua,load(EVIDENCE))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
