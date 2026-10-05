#!/usr/bin/env python3
"""V6.15.4 persistent source/evaluation storage.

Current visible source records are migrated once with their real first ingestion
time. Publication dates are never reused as fake first_fetched_at timestamps.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"docs"/"data"/"source_intelligence.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
EVENT_HISTORY=ROOT/"research"/"history"/"event_score_history.json"
VERSION="6.15.8l"

sys.path.insert(0,str(ROOT/"scripts"))
from source_intelligence_engine import collect_full_records,collect_full_records_with_accounting
from evaluation_spec import load_spec

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def digest(v):
    return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def source_key(r):
    return str(r.get("id") or r.get("url") or digest({"title":r.get("title"),"author":r.get("author")})[:20])

TRACKING_KEYS={"fbclid","gclid","mc_cid","mc_eid"}

def normalize_text(v):
    return re.sub(r"\\s+"," ",str(v or "").strip().lower())

def canonical_url(url):
    if not url:return ""
    try:
        p=urlsplit(str(url).strip())
        host=(p.hostname or "").lower()
        if host.startswith("www."):host=host[4:]
        netloc=host
        if p.port and not ((p.scheme.lower()=="http" and p.port==80) or (p.scheme.lower()=="https" and p.port==443)):
            netloc=f"{host}:{p.port}"
        path=p.path or "/"
        if path!="/":path=path.rstrip("/")
        pairs=[]
        for k,v in parse_qsl(p.query,keep_blank_values=True):
            lk=k.lower()
            if lk.startswith("utm_") or lk in TRACKING_KEYS:continue
            pairs.append((k,v))
        pairs.sort()
        return urlunsplit(("https",netloc,path,urlencode(pairs,doseq=True),""))
    except Exception:
        return ""

def published_calendar_date(v):
    if not v:return ""
    try:return str(datetime.fromisoformat(str(v).replace("Z","+00:00")).date())
    except Exception:
        try:return str(v)[:10]
        except Exception:return ""

def secondary_identity_fingerprint(r):
    payload={
        "title":normalize_text(r.get("title")),
        "author":normalize_text(r.get("author")),
        "published_date":published_calendar_date(r.get("published_at")),
    }
    if not any(payload.values()):return ""
    return digest(payload)

def identity_fields_from_row(row):
    rec=(row or {}).get("record") or {}
    return {
        "canonical_url":(row or {}).get("canonical_url") or canonical_url(rec.get("url")),
        "secondary_identity_fingerprint":(row or {}).get("secondary_identity_fingerprint") or secondary_identity_fingerprint(rec),
    }

def parse_aware(v):
    try:
        dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return dt if dt.tzinfo is not None else None
    except Exception:return None

def late_discovery_veto(r,ts,now,spec):
    cfg=((((spec or {}).get("definitions") or {}).get("point_in_time_eligibility") or {}).get("source_admission") or {})
    trusted=set(cfg.get("high_confidence_published_at_semantics") or [])
    if ts.get("published_at_semantics") not in trusted:return False,None
    pub_day=published_calendar_date(r.get("published_at"))
    seen=parse_aware(now)
    if not pub_day or seen is None:return False,None
    try: pub_date=datetime.fromisoformat(pub_day).date()
    except Exception:return False,None
    days=(seen.astimezone(timezone.utc).date()-pub_date).days
    limit=int(cfg.get("late_discovery_calendar_days_max",3))
    return days>limit,days

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

def migrate_sources(source,prior=None,now=None,full_records=None,upstream_accounting=None,spec=None):
    """Persist the full pre-window source stream.

    Existing rows keep their real first_fetched_at. Records newly recovered from
    outside the historical 800-row window are marked backfill_ingest and receive
    the actual recovery timestamp, never a fabricated earlier fetch date.
    """
    now=now or datetime.now(timezone.utc).isoformat()
    spec=spec or load_spec()
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
    old_url_index={}
    old_secondary_index={}
    for orow in old.values():
        ids=identity_fields_from_row(orow)
        if ids["canonical_url"]:old_url_index.setdefault(ids["canonical_url"],[]).append(orow)
        if ids["secondary_identity_fingerprint"]:old_secondary_index.setdefault(ids["secondary_identity_fingerprint"],[]).append(orow)

    batch_meta=[]
    batch_url_counts={}
    batch_secondary_counts={}
    for r in full:
        k=source_key(r);cu=canonical_url(r.get("url"));sf=secondary_identity_fingerprint(r)
        batch_meta.append((r,k,cu,sf))
        if cu:batch_url_counts.setdefault(cu,set()).add(k)
        if sf:batch_secondary_counts.setdefault(sf,set()).add(k)

    rows=[]
    for r,k,cu,sf in batch_meta:
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
        inherited=None
        identity_match_basis=None
        ambiguous=False
        age_days=None
        if not prev:
            hist_matches=[]
            if cu:hist_matches.extend(old_url_index.get(cu,[]))
            if sf:hist_matches.extend(old_secondary_index.get(sf,[]))
            uniq={x.get("source_key"):x for x in hist_matches if x.get("source_key")}
            if len(uniq)==1:
                inherited=next(iter(uniq.values()))
                identity_match_basis="canonical_url" if cu and inherited in old_url_index.get(cu,[]) else "secondary_fingerprint"
            elif len(uniq)>1:
                ambiguous=True
            if cu and len(batch_url_counts.get(cu,set()))>1:ambiguous=True
            if sf and len(batch_secondary_counts.get(sf,set()))>1:ambiguous=True

        if prev:
            admission_class=prev.get("admission_class") or (
                "initial_migration" if prev.get("ingest_type")=="initial_migration"
                else "backfill" if prev.get("ingest_type")=="backfill_ingest"
                else "legacy_live_unverified"
            )
            ingest_type=prev.get("ingest_type") or "initial_migration"
            admission_origin=prev.get("admission_origin") or "legacy_persisted_record"
            identity_parent_source_key=prev.get("identity_parent_source_key")
            first_source=prev
        elif inherited and not ambiguous:
            admission_class="rekeyed_duplicate"
            ingest_type=inherited.get("ingest_type") or "initial_migration"
            admission_origin="historical_identity_match"
            identity_parent_source_key=inherited.get("source_key")
            first_source=inherited
        elif ambiguous:
            admission_class="identity_ambiguous"
            ingest_type="backfill_ingest"
            admission_origin="identity_collision_fail_closed"
            identity_parent_source_key=None
            first_source=None
        elif not old:
            admission_class="initial_migration" if k in visible_keys else "backfill"
            ingest_type="initial_migration" if k in visible_keys else "backfill_ingest"
            admission_origin="foundation_initialization"
            identity_parent_source_key=None
            first_source=None
        elif k not in visible_keys:
            admission_class="backfill"
            ingest_type="backfill_ingest"
            admission_origin="outside_visible_window_recovery"
            identity_parent_source_key=None
            first_source=None
        else:
            veto,age_days=late_discovery_veto(r,ts,now,spec)
            admission_class="late_discovery" if veto else "genuine_forward"
            ingest_type="backfill_ingest" if veto else "live_ingest"
            admission_origin="high_confidence_late_discovery_veto" if veto else "new_visible_source_no_prior_identity_match"
            identity_parent_source_key=None
            first_source=None
        current_snapshot_hash=digest(snap)
        snapshot_history=list((prev or {}).get("snapshot_history") or [])
        if prev and prev.get("snapshot_hash") and prev.get("snapshot_hash")!=current_snapshot_hash:
            old_hash=prev.get("snapshot_hash")
            if old_hash not in snapshot_history:snapshot_history.append(old_hash)
        rows.append({
            "source_key":k,
            "first_fetched_at":(first_source or {}).get("first_fetched_at") or now,
            "first_fetched_at_origin":(first_source or {}).get("first_fetched_at_origin") or "source_store_first_observation",
            "last_seen_at":now,
            "ingest_type":ingest_type,
            "admission_class":admission_class,
            "admission_origin":admission_origin,
            "admission_classified_at":(prev or inherited or {}).get("admission_classified_at") or now,
            "identity_parent_source_key":identity_parent_source_key,
            "identity_match_basis":identity_match_basis,
            "canonical_url":cu,
            "secondary_identity_fingerprint":sf,
            "late_discovery_age_calendar_days":age_days,
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
            "admission_class_counts":{k:sum(1 for x in rows if x.get("admission_class")==k) for k in sorted({x.get("admission_class") for x in rows if x.get("admission_class")})},
            "low_confidence_genuine_forward_records":sum(1 for x in rows if x.get("admission_class")=="genuine_forward" and x.get("timestamp_confidence")!="high"),
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
    out=migrate_sources(source,load(SOURCE_STORE,{}),now,full_records=full,upstream_accounting=upstream_accounting,spec=load_spec())
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
