#!/usr/bin/env python3
"""V6.15.1 immutable Rule Registry.

Builds stable rule identities from semantic content, not operation position.
Output is research-only and append-friendly.
"""
from __future__ import annotations
import hashlib, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
READING=ROOT/"docs"/"research"/"source_reading_memory.json"
SOURCE=ROOT/"docs"/"data"/"source_intelligence.json"
OUT=ROOT/"research"/"registry"/"rules.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
VERSION="6.15.8d"

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def sha(v):
    return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def normalize_rule(rule):
    fields={k:rule.get("fields",{}).get(k) for k in sorted((rule.get("fields") or {}))}
    conditions=sorted(str(x).strip() for x in (rule.get("conditions") or []) if str(x).strip())
    actions=sorted(str(x).strip().lower() for x in (rule.get("actions") or []) if str(x).strip())
    return {"fields":fields,"conditions":conditions,"actions":actions}

def source_snapshot(record):
    return {
        "source_id":record.get("source_id"),
        "author":record.get("author"),
        "published_at":record.get("published_at"),
        "title":record.get("title"),
        "url":record.get("url"),
        "symbols":record.get("symbols") or [],
    }

def overlapping_operation_consistency(source):
    records={str(r.get("id")):r for r in (source.get("records") or []) if r.get("id") is not None}
    problems=[]
    for case in source.get("operation_cases") or []:
        rid=str(case.get("id"))
        if rid not in records:
            continue
        if sha(records[rid].get("operations") or []) != sha(case.get("operations") or []):
            problems.append(rid)
    if problems:
        raise ValueError("records.operations != operation_cases.operations for: "+",".join(problems[:10]))
    return {"checked":sum(1 for c in (source.get("operation_cases") or []) if str(c.get("id")) in records),"mismatches":0}

def build(reading,source,prior=None,now=None,source_store=None):
    now=now or datetime.now(timezone.utc).isoformat()
    consistency=overlapping_operation_consistency(source)
    prior_by_id={r["rule_id"]:r for r in ((prior or {}).get("rules") or [])}
    prior_observations={str(x.get("source_id")):x for x in ((prior or {}).get("source_observations") or []) if x.get("source_id")}
    observation_feature_preexisting="source_observations" in (prior or {})
    source_meta={}
    for row in (source_store or {}).get("records") or []:
        rec=row.get("record") or {}
        sid=str(rec.get("id") or row.get("source_key") or "")
        if sid: source_meta[sid]=row

    current_observations=[]
    seen_observation_ids=set()
    reading_records=list(reading.get("records") or [])
    for rec in reading_records:
        sid=str(rec.get("source_id") or "")
        if not sid: continue
        old_obs=prior_observations.get(sid)
        meta=source_meta.get(sid) or {}
        seen_observation_ids.add(sid)
        current_observations.append({
            "source_id":sid,
            "first_registry_seen_at":(old_obs or {}).get("first_registry_seen_at") or now,
            "last_registry_seen_at":now,
            "first_extractor_version":(old_obs or {}).get("first_extractor_version") or reading.get("version"),
            "first_extractor_input_hash":(old_obs or {}).get("first_extractor_input_hash") or rec.get("extractor_input_hash"),
            "latest_extractor_version":reading.get("version"),
            "latest_extractor_input_hash":rec.get("extractor_input_hash"),
            "source_admission_class":meta.get("admission_class"),
            "source_first_fetched_at":meta.get("first_fetched_at"),
        })

    for sid,old_obs in prior_observations.items():
        if sid not in seen_observation_ids:
            current_observations.append(dict(old_obs))

    candidates=[]
    for rec in reading_records:
        sid=str(rec.get("source_id") or "")
        for prop in rec.get("propositions") or []:
            if prop.get("kind")!="testable_rule":continue
            ev=prop.get("evidence") or {}
            rule=normalize_rule(ev.get("rule") or {})
            methods=sorted(ev.get("method_candidates") or [])
            snap=source_snapshot(rec)
            normalized_payload={
                "source_id":sid,
                "rule":rule,
                "symbols":sorted(rec.get("symbols") or []),
                "attribution":ev.get("attribution"),
            }
            semantic_hash=sha(normalized_payload)
            candidates.append({
                "_semantic_hash":semantic_hash,
                "_old_operation_index":ev.get("operation_index"),
                "source_id":sid,
                "source_snapshot_hash":sha(snap),
                "extractor_input_hash":rec.get("extractor_input_hash"),
                "extractor_input_scope":rec.get("extractor_input_scope"),
                "normalized_rule_hash":sha(rule),
                "normalized_rule":rule,
                "symbols":sorted(rec.get("symbols") or []),
                "attribution":ev.get("attribution"),
                "method_candidates":methods,
                "author":rec.get("author"),
                "published_at":rec.get("published_at"),
                "url":rec.get("url"),
                "title":rec.get("title"),
            })

    groups=defaultdict(list)
    for c in candidates: groups[(c["source_id"],c["_semantic_hash"])].append(c)
    rules=[]
    legacy_map=[]
    for (sid,semhash),rows in sorted(groups.items()):
        rows=sorted(rows,key=lambda x:(x["_old_operation_index"] is None,x["_old_operation_index"] if x["_old_operation_index"] is not None else 999999))
        for duplicate_rank,row in enumerate(rows,1):
            rid="rule_"+hashlib.sha256(f"{sid}|{semhash}|dup:{duplicate_rank}".encode()).hexdigest()[:24]
            old=prior_by_id.get(rid)
            out={k:v for k,v in row.items() if not k.startswith("_")}
            current_extractor_hash=row.get("extractor_input_hash")
            revisions=list((old or {}).get("extractor_input_revisions") or [])
            if old and old.get("extractor_input_hash") and old.get("extractor_input_hash")!=current_extractor_hash:
                prior_hash=old.get("extractor_input_hash")
                if not any(x.get("extractor_input_hash")==prior_hash for x in revisions):
                    revisions.append({
                        "extractor_input_hash":prior_hash,
                        "extractor_version":old.get("extractor_version"),
                        "recorded_at":old.get("last_seen_at") or old.get("first_seen_at"),
                    })
            meta=source_meta.get(sid) or {}
            prior_obs=prior_observations.get(sid)
            if old:
                extraction_mode=old.get("extraction_mode")
                forward_eligible=old.get("forward_eligible")
            elif not observation_feature_preexisting:
                # One-time migration baseline: never retroactively assert that
                # legacy rules were forward-created before source-observation
                # tracking existed.
                extraction_mode="legacy_baseline"
                forward_eligible=None
            elif meta.get("admission_class")=="genuine_forward" and prior_obs is None:
                extraction_mode="forward_initial"
                forward_eligible=True
            elif meta.get("admission_class")=="genuine_forward":
                extraction_mode="retroactive"
                forward_eligible=False
            else:
                extraction_mode="historical_or_nonforward"
                forward_eligible=False
            out.update({
                "rule_id":rid,
                "semantic_hash":semhash,
                "duplicate_rank":duplicate_rank,
                "extractor_version":reading.get("version"),
                "extractor_input_revisions":revisions,
                "first_seen_at":(old or {}).get("first_seen_at") or now,
                "last_seen_at":now,
                "extraction_mode":extraction_mode,
                "forward_eligible":forward_eligible,
                "supersedes":(old or {}).get("supersedes"),
                "superseded_by":(old or {}).get("superseded_by"),
                "active":True,
            })
            rules.append(out)
            legacy_map.append({
                "source_id":sid,
                "operation_index":row["_old_operation_index"],
                "rule_id":rid,
                "legacy_key":f"{sid}:{row['_old_operation_index']}",
                "normalized_rule_hash":row["normalized_rule_hash"],
            })
    current_ids={r["rule_id"] for r in rules}
    for rid,old in prior_by_id.items():
        if rid not in current_ids:
            archived=dict(old);archived["active"]=False;archived["last_seen_at"]=old.get("last_seen_at") or now
            rules.append(archived)

    return {
        "version":VERSION,
        "generated_at":now,
        "mode":"research_only_append_registry",
        "source_reading_version":reading.get("version"),
        "operation_consistency":consistency,
        "counts":{"rules":len(rules),"active":sum(1 for r in rules if r.get("active")),"legacy_mappings":len(legacy_map)},
        "rules":rules,
        "source_observations":sorted(current_observations,key=lambda x:x["source_id"]),
        "legacy_mapping":legacy_map,
        "guardrails":[
            "Rule identity is semantic and independent of operation ordering.",
            "Exact duplicate semantic rules remain separate via deterministic duplicate_rank.",
            "Prior registry rows are never deleted; absent rules become inactive.",
            "Exact extractor-input hashes are retained, and changed inputs append their prior hash to revision history.",
            "A genuine-forward source may create forward-eligible rules only on its first registry observation; later newly-created rules are retroactive and forward_eligible=false.",
            "Registry cannot modify production rules or orders."
        ]
    }

def main():
    prior=load(OUT,{})
    out=build(load(READING,{}),load(SOURCE,{}),prior,source_store=load(SOURCE_STORE,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
