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
                "count as one independent evidence item; duplicates cannot form independent method/candidate evidence."),
    }

def main():
    rows=sie.collect_full_records()
    out=build(rows)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
