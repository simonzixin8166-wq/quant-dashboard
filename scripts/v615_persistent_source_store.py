#!/usr/bin/env python3
"""V6.15.4 persistent source/evaluation storage.

Current visible source records are migrated once with their real first ingestion
time. Publication dates are never reused as fake first_fetched_at timestamps.
"""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"docs"/"data"/"source_intelligence.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
EVENT_HISTORY=ROOT/"research"/"history"/"event_score_history.json"
VERSION="6.15.4"

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def digest(v):
    return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def source_key(r):
    return str(r.get("id") or r.get("url") or digest({"title":r.get("title"),"author":r.get("author")})[:20])

def migrate_sources(source,prior=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    old={x["source_key"]:x for x in ((prior or {}).get("records") or [])}
    rows=[]
    for r in source.get("records") or []:
        k=source_key(r)
        snap={
            "id":r.get("id"),"source":r.get("source"),"source_kind":r.get("source_kind"),
            "author":r.get("author"),"published_at":r.get("published_at"),"title":r.get("title"),
            "url":r.get("url"),"symbols":r.get("symbols") or [],"topics":r.get("topics") or [],
            "operations":r.get("operations") or [],
        }
        prev=old.get(k)
        rows.append({
            "source_key":k,
            "first_fetched_at":(prev or {}).get("first_fetched_at") or now,
            "last_seen_at":now,
            "published_at":r.get("published_at"),
            "snapshot_hash":digest(snap),
            "source_still_online":None,
            "record":snap,
        })
    current={x["source_key"] for x in rows}
    for k,prev in old.items():
        if k not in current:
            p=dict(prev);p["source_still_online"]=False
            rows.append(p)
    return {
        "version":VERSION,"generated_at":now,
        "migration_note":"Visible records are first-ingested at actual migration time; publication dates are not reused as fetch timestamps.",
        "source_window_reported_total":int((source.get("counts") or {}).get("records") or len(source.get("records") or [])),
        "visible_window_size":len(source.get("records") or []),
        "records":rows,
    }

def append_event_history(events,prior=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    rows=list((prior or {}).get("records") or [])
    seen={(x.get("event_id"),x.get("spec_version"),x.get("score_hash")) for x in rows}
    added=0
    for e in events.get("events") or []:
        h=digest(e)
        key=(e.get("event_id"),e.get("spec_version"),h)
        if key in seen:continue
        rows.append({
            "event_id":e.get("event_id"),
            "rule_id":e.get("rule_id"),
            "spec_version":e.get("spec_version"),
            "score_hash":h,
            "recorded_at":now,
            "score":e,
        });seen.add(key);added+=1
    return {"version":VERSION,"generated_at":now,"records":rows,"added":added}

def main():
    now=datetime.now(timezone.utc).isoformat()
    src=migrate_sources(load(SOURCE,{}),load(SOURCE_STORE,{}),now)
    hist=append_event_history(load(EVENTS,{}),load(EVENT_HISTORY,{}),now)
    SOURCE_STORE.parent.mkdir(parents=True,exist_ok=True)
    EVENT_HISTORY.parent.mkdir(parents=True,exist_ok=True)
    SOURCE_STORE.write_text(json.dumps(src,ensure_ascii=False,indent=2),encoding="utf-8")
    EVENT_HISTORY.write_text(json.dumps(hist,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"sources":len(src["records"]),"history":len(hist["records"]),"added":hist["added"]},ensure_ascii=False))

if __name__=="__main__":main()
