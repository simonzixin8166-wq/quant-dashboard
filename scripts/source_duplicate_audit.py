#!/usr/bin/env python3
"""Cross-channel source duplicate map.

Preserves every source record while identifying exact normalized evidence copies
across blog/forum/video-like channels. The map is derived/rebuildable and does
not rewrite immutable Source Store provenance.
"""
from __future__ import annotations
import hashlib,json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"source_duplicate_map.json"
STORE=ROOT/"research"/"store"/"source_store.json"
sys.path.insert(0,str(ROOT/"scripts"))
import source_intelligence_engine as sie

def norm(v):
    s=re.sub(r"\s+"," ",str(v or "")).strip().casefold()
    return s

def signature(row):
    title=norm(row.get("title"))
    excerpt=norm(row.get("excerpt"))
    # Cross-channel evidence identity must be author-independent. Otherwise the
    # same copied/reposted text attributed through a different channel/author
    # would incorrectly count as independent corroboration.
    #
    # Keep this deliberately exact/conservative: title + excerpt must match
    # after whitespace/case normalization, and very short generic replies are
    # never deduplicated.
    payload="|".join([title,excerpt])
    if len(title)+len(excerpt)<60:
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

NEAR_MIN_CHARS=80
NEAR_JACCARD=0.90
NEAR_MAX_DAYS=2

def _compact(v):
    return re.sub(r"\s+","",str(v or "")).casefold()

def _grams(s,k=3):
    return {s[i:i+k] for i in range(max(0,len(s)-k+1))}

def _pub_date(row):
    from datetime import date
    try:return date.fromisoformat(str(row.get("published_at") or "")[:10])
    except Exception:return None

def near_duplicate(a,b):
    """Same author repost across channels: near-identical text within a few days.

    Deliberately strict: titles may differ (forum reposts often prefix them),
    but the text must be near-identical, so same-topic articles with a different
    date or different hypothesis are never merged.
    """
    if not a.get("author") or a.get("author")!=b.get("author"):return False
    if str(a.get("source_kind") or "")==str(b.get("source_kind") or ""):return False
    da,db=_pub_date(a),_pub_date(b)
    if da is None or db is None or abs((da-db).days)>NEAR_MAX_DAYS:return False
    ta,tb=_compact(a.get("excerpt")),_compact(b.get("excerpt"))
    if len(ta)<NEAR_MIN_CHARS or len(tb)<NEAR_MIN_CHARS:return False
    ga,gb=_grams(ta),_grams(tb)
    return bool(ga and gb) and len(ga&gb)/len(ga|gb)>=NEAR_JACCARD

def build(rows):
    groups={}
    for row in rows:
        sig=signature(row)
        if not sig:continue
        groups.setdefault(sig,[]).append(row)
    mapping={}
    duplicate_groups=0
    duplicate_records=0
    for sig,items in groups.items():
        channels={str(x.get("source_kind") or x.get("source") or "") for x in items}
        if len(items)<2 or len(channels)<2:
            continue
        duplicate_groups+=1
        ordered=sorted(items,key=lambda x:(str(x.get("captured_at") or ""),str(x.get("id") or x.get("url") or "")))
        canonical=ordered[0]
        canonical_id=str(canonical.get("id") or canonical.get("url") or "")
        for item in ordered:
            sid=str(item.get("id") or item.get("url") or "")
            is_dup=sid!=canonical_id
            if is_dup:duplicate_records+=1
            mapping[sid]={
                "content_hash":sig,
                "canonical_source_id":canonical_id,
                "duplicate_of":canonical_id if is_dup else None,
                "evidence_weight_class":"duplicate_evidence" if is_dup else "canonical_evidence",
                "channels":sorted(channels),
            }
    exact_groups=duplicate_groups
    for sid in mapping:mapping[sid]["match_basis"]="exact_text"

    # Near-duplicate pass over records not already grouped (union-find).
    free=[r for r in rows if str(r.get("id") or r.get("url") or "") not in mapping]
    by_author={}
    for r in free:by_author.setdefault(str(r.get("author") or ""),[]).append(r)
    parent={}
    def find(x):
        while parent.get(x,x)!=x:x=parent[x]
        return x
    for author,items in by_author.items():
        if not author:continue
        for i in range(len(items)):
            for j in range(i+1,len(items)):
                if near_duplicate(items[i],items[j]):
                    a=str(items[i].get("id") or items[i].get("url"));b=str(items[j].get("id") or items[j].get("url"))
                    parent[find(a)]=find(b)
    clusters={}
    index={str(r.get("id") or r.get("url") or ""):r for r in free}
    for sid in list(parent)+[p for p in parent.values()]:
        if sid in index:clusters.setdefault(find(sid),set()).add(sid)
    near_groups=0
    for members in clusters.values():
        if len(members)<2:continue
        near_groups+=1;duplicate_groups+=1
        items=sorted((index[m] for m in members),key=lambda x:(str(x.get("captured_at") or ""),str(x.get("id") or x.get("url") or "")))
        canonical_id=str(items[0].get("id") or items[0].get("url") or "")
        channels=sorted({str(x.get("source_kind") or x.get("source") or "") for x in items})
        for item in items:
            sid=str(item.get("id") or item.get("url") or "")
            is_dup=sid!=canonical_id
            if is_dup:duplicate_records+=1
            mapping[sid]={
                "content_hash":hashlib.sha256(_compact(item.get("excerpt")).encode("utf-8")).hexdigest(),
                "canonical_source_id":canonical_id,
                "duplicate_of":canonical_id if is_dup else None,
                "evidence_weight_class":"duplicate_evidence" if is_dup else "canonical_evidence",
                "channels":channels,
                "match_basis":"near_text_same_author",
            }
    return {
      "version":3,
      "counts":{"records_scanned":len(rows),"duplicate_groups":duplicate_groups,"duplicate_records":duplicate_records,
                "exact_groups":exact_groups,"near_groups":near_groups},
      "mapping":mapping,
      "policy":("All raw sources are retained with provenance. Exact normalized cross-channel copies, and same-author "
                f"cross-channel reposts with near-identical text (3-gram Jaccard >= {NEAR_JACCARD}, within {NEAR_MAX_DAYS} days), "
                "count as one independent evidence item; two Store identities of the same canonical URL count once; duplicates cannot "
                "form independent method/candidate evidence."),
    }

def _url_key(u):
    # exact canonical URL only: forum posts differ only in their query string, so it must never be stripped
    return str(u or "").strip()

def store_identity_duplicates(store_rows,feed_ids,mapping):
    """SRC-04: the canonical Store can hold two identities for one article (a seed/migration record and the
    research-stream record of the same URL, e.g. 3 BrightLine blog posts of 2026-09). Same channel, so the
    cross-channel passes never see them, but Source Reading reads every Store row and would count the article
    twice. Group Store rows by canonical URL; the canonical is the identity present in the normalized feed
    (else the earliest first_fetched_at); the others are registered duplicate_of it. Nothing is deleted."""
    groups={}
    for row in store_rows or []:
        rec=row.get("record") or {}
        key=_url_key(row.get("canonical_url") or rec.get("url"))
        sid=str(rec.get("id") or rec.get("url") or "")
        if key and sid:groups.setdefault(key,[]).append((row,sid))
    added=0;n=0
    for key,items in groups.items():
        ids={sid for _,sid in items}
        if len(ids)<2:continue
        if any(sid in mapping for sid in ids):continue      # already explained by a text pass
        n+=1
        ordered=sorted(items,key=lambda x:(x[1] not in feed_ids,str(x[0].get("first_fetched_at") or ""),x[1]))
        canonical_id=ordered[0][1]
        channels=sorted({str((r.get("record") or {}).get("source_kind") or "") for r,_ in items})
        for row,sid in ordered:
            is_dup=sid!=canonical_id
            if is_dup:added+=1
            mapping[sid]={
                "content_hash":hashlib.sha256(key.encode("utf-8")).hexdigest(),
                "canonical_source_id":canonical_id,
                "duplicate_of":canonical_id if is_dup else None,
                "evidence_weight_class":"duplicate_evidence" if is_dup else "canonical_evidence",
                "channels":channels,
                "match_basis":"same_canonical_url",
            }
    return n,added

def main():
    rows=sie.collect_full_records()
    out=build(rows)
    try:
        store=json.loads(STORE.read_text(encoding="utf-8")).get("records") or []
        store_status="ok"
    except Exception as exc:  # fail-soft: the text passes still run; the gap is visible
        store,store_status=[],f"unavailable:{type(exc).__name__}"
    feed_ids={str(r.get("id") or r.get("url") or "") for r in rows}
    url_groups,url_dups=store_identity_duplicates(store,feed_ids,out["mapping"])
    out["counts"].update({"store_scanned":len(store),"store_status":store_status,"url_groups":url_groups})
    out["counts"]["duplicate_groups"]+=url_groups
    out["counts"]["duplicate_records"]+=url_dups
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
