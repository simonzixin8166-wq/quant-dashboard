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
    return {
      "version":2,
      "counts":{"records_scanned":len(rows),"duplicate_groups":duplicate_groups,"duplicate_records":duplicate_records},
      "mapping":mapping,
      "policy":"All raw sources are retained. Exact normalized cross-channel copies are author-independent and may not count as independent method/candidate evidence.",
    }

def main():
    rows=sie.collect_full_records()
    out=build(rows)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
