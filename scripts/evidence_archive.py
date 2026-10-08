#!/usr/bin/env python3
"""Append-only canonical archive for SEC filings and event/news evidence.

Current-view artifacts may stay bounded for UI/research context. This archive is
the durable evidence history used for later learning/reconciliation.
"""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT/"docs"/"research"/"official_evidence.json"
EVENTS=ROOT/"docs"/"research"/"event_evidence.json"
ARCHIVE_ROOT=ROOT/"research"/"archive"
MANIFEST=ARCHIVE_ROOT/"evidence_archive_manifest.json"

def load(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def stable_id(prefix,*parts):
    raw="|".join(str(x or "") for x in parts)
    return prefix+"_"+hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

def month_for(value, fallback):
    s=str(value or "")[:7]
    return s if len(s)==7 and s[4]=="-" else fallback[:7]

def read_ids(folder):
    ids=set()
    if not folder.exists():return ids
    for path in folder.glob("*.jsonl"):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():continue
                row=json.loads(line)
                if row.get("archive_id"):ids.add(str(row["archive_id"]))
        except Exception:
            continue
    return ids

def append_rows(folder,rows,now):
    folder.mkdir(parents=True,exist_ok=True)
    known=read_ids(folder)
    added=0
    handles={}
    try:
        for row in rows:
            aid=str(row.get("archive_id") or "")
            if not aid or aid in known:continue
            month=month_for(row.get("event_date") or row.get("filing_date") or row.get("published_at"),now)
            path=folder/f"{month}.jsonl"
            fh=handles.get(path)
            if fh is None:
                fh=path.open("a",encoding="utf-8")
                handles[path]=fh
            fh.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
            known.add(aid);added+=1
    finally:
        for fh in handles.values():fh.close()
    return added,len(known)

def official_rows(doc,now):
    rows=[]
    for symbol,node in (doc.get("symbols") or {}).items():
        for filing in node.get("filings") or []:
            accession=filing.get("accession")
            aid=stable_id("sec",symbol,accession or filing.get("url"),filing.get("filing_date"),filing.get("form"))
            rows.append({
                "archive_id":aid,"archive_kind":"sec_filing","archived_at":now,
                "symbol":symbol,"cik":node.get("cik"),"company_name":node.get("company_name"),
                "form":filing.get("form"),"accession":accession,
                "filing_date":filing.get("filing_date"),"report_date":filing.get("report_date"),
                "primary_document":filing.get("primary_document"),"url":filing.get("url"),
                "document_status":filing.get("document_status"),
                "excerpts":filing.get("excerpts") or [],
                "source":"SEC EDGAR official","source_snapshot_generated_at":doc.get("generated_at"),
                "forward_evidence_eligible":False,
            })
    return rows

def event_rows(doc,now):
    rows=[]
    for symbol,node in (doc.get("symbols") or {}).items():
        for item in node.get("news") or []:
            aid=stable_id("event",symbol,item.get("uuid") or item.get("url"),item.get("published_at"),item.get("title"))
            rows.append({
                "archive_id":aid,"archive_kind":"news_event","archived_at":now,
                "symbol":symbol,"event_date":item.get("published_at"),
                "published_at":item.get("published_at"),"title":item.get("title"),
                "publisher":item.get("publisher"),"source_type":item.get("source_type"),
                "source_priority":item.get("source_priority"),"url":item.get("url"),
                "uuid":item.get("uuid"),"related_tickers":item.get("related_tickers") or [],
                "source_snapshot_generated_at":doc.get("generated_at"),
                "used_in_decision":False,
            })
    return rows

def build(official,event,archive_root=ARCHIVE_ROOT,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    sec_new,sec_total=append_rows(Path(archive_root)/"sec_filings",official_rows(official,now),now)
    event_new,event_total=append_rows(Path(archive_root)/"events",event_rows(event,now),now)
    return {
        "version":1,"generated_at":now,
        "retention_policy":"append_only_monthly_jsonl_no_record_count_cap",
        "sec":{"new":sec_new,"total":sec_total},
        "events":{"new":event_new,"total":event_total},
        "guardrails":[
            "Bounded current-view artifacts are presentation/context only; canonical history lives here.",
            "Archive rows are immutable by archive_id and never directly mutate Production rules.",
            "SEC remains higher-authority than media evidence."
        ],
    }

def main():
    out=build(load(OFFICIAL,{}),load(EVENTS,{}))
    MANIFEST.parent.mkdir(parents=True,exist_ok=True)
    MANIFEST.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))

if __name__=="__main__":main()
