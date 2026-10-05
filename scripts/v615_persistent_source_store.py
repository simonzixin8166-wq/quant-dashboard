#!/usr/bin/env python3
"""V6.15.4 persistent source/evaluation storage.

Current visible source records are migrated once with their real first ingestion
time. Publication dates are never reused as fake first_fetched_at timestamps.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"docs"/"data"/"source_intelligence.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
EVENT_HISTORY=ROOT/"research"/"history"/"event_score_history.json"
VERSION="6.15.8i"

sys.path.insert(0,str(ROOT/"scripts"))
from source_intelligence_engine import collect_full_records,collect_full_records_with_accounting

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def digest(v):
    return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def source_key(r):
    return str(r.get("id") or r.get("url") or digest({"title":r.get("title"),"author":r.get("author")})[:20])

def timestamp_metadata(r):
    source=str(r.get("source") or "").lower()
    kind=str(r.get("source_kind") or "").lower()
    published=bool(r.get("published_at"))
    if source=="wenxuecity" and kind=="blog" and published:
        return {
            "published_at_semantics":"source_archive_publication_date",
            "timestamp_confidence":"high",
        }
    return {
        "published_at_semantics":"upstream_published_at_unverified" if published else "missing_published_at",
        "timestamp_confidence":"unverified" if published else "missing",
    }

def migrate_sources(source,prior=None,now=None,full_records=None,upstream_accounting=None):
    """Persist the full pre-window source stream.

    Existing rows keep their real first_fetched_at. Records newly recovered from
    outside the historical 800-row window are marked backfill_ingest and receive
    the actual recovery timestamp, never a fabricated earlier fetch date.
    """
    now=now or datetime.now(timezone.utc).isoformat()
    old={x["source_key"]:x for x in ((prior or {}).get("records") or [])}
    visible_keys={source_key(r) for r in (source.get("records") or [])}
    legacy_reported_total=int((source.get("counts") or {}).get("records") or len(source.get("records") or []))
    full=list(full_records if full_records is not None else (source.get("records") or []))
    upstream_accounting=dict(upstream_accounting or {
        "upstream_raw_records":len(full),
        "eligible_raw_records":len(full),
        "normalized_unique_records":max(len(full),legacy_reported_total),
        "duplicates_removed":0,
        "excluded_missing_identity":0,
        "reconciliation_ok":True,
    })
    upstream_unique=int(upstream_accounting.get("normalized_unique_records") or 0)
    if not upstream_accounting.get("reconciliation_ok"):
        raise RuntimeError("upstream source reconciliation failed")
    if len(full) != upstream_unique:
        raise RuntimeError(
            f"current normalized ingest mismatch: full={len(full)} upstream_unique={upstream_unique}"
        )
    rows=[]
    for r in full:
        k=source_key(r)
        snap={
            "id":r.get("id"),"source":r.get("source"),"source_kind":r.get("source_kind"),
            "author":r.get("author"),"published_at":r.get("published_at"),"title":r.get("title"),
            "url":r.get("url"),"symbols":r.get("symbols") or [],"topics":r.get("topics") or [],
            "operations":r.get("operations") or [],
            "content_chars":r.get("content_chars"),
        }
        normalized_text_payload={"title":r.get("title") or "","excerpt":r.get("excerpt") or ""}
        operation_anchors=[
            op.get("anchor_index") for op in (r.get("operations") or [])
            if isinstance(op,dict) and op.get("anchor_index") is not None
        ]
        prev=old.get(k)
        ts=timestamp_metadata(r)
        if prev:
            ingest_type=prev.get("ingest_type") or "initial_migration"
        elif not old:
            ingest_type="initial_migration" if k in visible_keys else "backfill_ingest"
        else:
            ingest_type="live_ingest" if k in visible_keys else "backfill_ingest"
        current_snapshot_hash=digest(snap)
        snapshot_history=list((prev or {}).get("snapshot_history") or [])
        if prev and prev.get("snapshot_hash") and prev.get("snapshot_hash")!=current_snapshot_hash:
            old_hash=prev.get("snapshot_hash")
            if old_hash not in snapshot_history:snapshot_history.append(old_hash)
        rows.append({
            "source_key":k,
            "first_fetched_at":(prev or {}).get("first_fetched_at") or now,
            "last_seen_at":now,
            "ingest_type":ingest_type,
            "published_at":r.get("published_at"),
            **ts,
            "snapshot_hash":current_snapshot_hash,
            "snapshot_history":snapshot_history,
            "normalized_available_text_hash":digest(normalized_text_payload),
            "content_hash_scope":"normalized_title_excerpt_only",
            "raw_fulltext_hash_status":"unavailable_unless_preserved_by_upstream_source",
            "operation_anchor_indexes":operation_anchors,
            "source_still_online":None,
            "record":snap,
        })
    current={x["source_key"] for x in rows}
    retained_historical=0
    for k,prev in old.items():
        if k not in current:
            x=dict(prev);x["source_still_online"]=False
            rows.append(x)
            retained_historical+=1
    if len(current) != upstream_unique:
        raise AssertionError(f"current source keys {len(current)} != upstream unique records {upstream_unique}")
    return {
        "version":VERSION,"generated_at":now,
        "migration_note":"Persistent ingestion uses the complete pre-window normalized stream. Newly recovered historical rows use real backfill ingestion time; publication dates are never reused as fetch timestamps.",
        "source_window_reported_total":legacy_reported_total,
        "legacy_reported_total":legacy_reported_total,
        "legacy_reported_total_role":"non_gating_snapshot_from_docs_source_intelligence",
        "visible_window_size":len(source.get("records") or []),
        "full_ingest_size":len(full),
        "upstream_reconciliation":upstream_accounting,
        "source_accounting":{
            "current_upstream_records":upstream_unique,
            "current_ingested_unique_records":len(current),
            "persistent_records_total":len(rows),
            "retained_historical_records":retained_historical,
            "legacy_reported_normalized_total":legacy_reported_total,
            "current_ingest_complete":bool(upstream_accounting.get("reconciliation_ok")) and len(current)==upstream_unique,
        },
        "records":rows,
    }

def append_event_history(events,prior=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    rows=list((prior or {}).get("records") or [])
    seen={(x.get("event_id"),x.get("spec_version"),x.get("scoring_engine_version"),x.get("score_hash")) for x in rows}
    added=0
    for e in events.get("events") or []:
        h=digest(e)
        engine=e.get("scoring_engine_version")
        key=(e.get("event_id"),e.get("spec_version"),engine,h)
        if key in seen:continue
        rows.append({
            "event_id":e.get("event_id"),
            "rule_id":e.get("rule_id"),
            "spec_version":e.get("spec_version"),
            "scoring_engine_version":engine,
            "score_hash":h,
            "recorded_at":now,
            "score":e,
        });seen.add(key);added+=1
    return {"version":VERSION,"generated_at":now,"records":rows,"added":added}

def select_current_event_records(history,spec_version):
    """Return exactly one current effective revision per event for an active spec.

    Append-only history is audit provenance only; duplicate engine revisions under
    the same spec must never multiply statistical sample size.
    """
    chosen={}
    for row in history.get("records") or []:
        if str(row.get("spec_version"))!=str(spec_version):
            continue
        eid=str(row.get("event_id") or "")
        prior=chosen.get(eid)
        if prior is None or str(row.get("recorded_at") or "") >= str(prior.get("recorded_at") or ""):
            chosen[eid]=row
    return [chosen[k] for k in sorted(chosen)]

def build_source_store(now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    source=load(SOURCE,{})
    full,upstream_accounting=collect_full_records_with_accounting()
    out=migrate_sources(source,load(SOURCE_STORE,{}),now,full_records=full,upstream_accounting=upstream_accounting)
    SOURCE_STORE.parent.mkdir(parents=True,exist_ok=True)
    SOURCE_STORE.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    return out

def build_event_history(now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    hist=append_event_history(load(EVENTS,{}),load(EVENT_HISTORY,{}),now)
    EVENT_HISTORY.parent.mkdir(parents=True,exist_ok=True)
    EVENT_HISTORY.write_text(json.dumps(hist,ensure_ascii=False,indent=2),encoding="utf-8")
    return hist

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sources-only",action="store_true")
    parser.add_argument("--events-only",action="store_true")
    args=parser.parse_args()
    now=datetime.now(timezone.utc).isoformat()
    src=None;hist=None
    if not args.events_only:
        src=build_source_store(now)
    if not args.sources_only:
        hist=build_event_history(now)
    print(json.dumps({
        "sources":len((src or {}).get("records") or []) if src is not None else None,
        "full_ingest_size":(src or {}).get("full_ingest_size") if src is not None else None,
        "source_accounting":(src or {}).get("source_accounting") if src is not None else None,
        "history":len((hist or {}).get("records") or []) if hist is not None else None,
        "added":(hist or {}).get("added") if hist is not None else None,
    },ensure_ascii=False))

if __name__=="__main__":main()
