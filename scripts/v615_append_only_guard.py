#!/usr/bin/env python3
"""V6.15.8d append-only invariants for research history/registry stores."""
from __future__ import annotations
import json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGETS={
 "event_history":ROOT/"research/history/event_score_history.json",
 "rules":ROOT/"research/registry/rules.json",
 "source_store":ROOT/"research/store/source_store.json",
 "contradictions":ROOT/"research/history/contradictions.json",
 "source_rule_funnel_history":ROOT/"research/history/source_rule_funnel_history.json",
}
VERSION="6.15.8l"

def load_text_json(text,default=None):
    try:return json.loads(text)
    except Exception:return {} if default is None else default

def load(path,default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def head_json(rel):
    # Missing-in-HEAD is a legitimate empty baseline. Any other git failure
    # must fail closed so immutable provenance cannot silently lose protection.
    try:
        subprocess.check_output(["git","rev-parse","--verify","HEAD"],cwd=ROOT,text=True,stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise RuntimeError(f"cannot resolve HEAD while reading {rel}") from exc
    probe=subprocess.run(["git","cat-file","-e",f"HEAD:{rel}"],cwd=ROOT,text=True,capture_output=True)
    if probe.returncode!=0:
        tree=subprocess.run(["git","ls-tree","--name-only","HEAD","--",rel],cwd=ROOT,text=True,capture_output=True)
        if tree.returncode==0 and not tree.stdout.strip():
            return {}
        raise RuntimeError(f"cannot read HEAD:{rel}: {probe.stderr or tree.stderr}")
    try:
        text=subprocess.check_output(["git","show",f"HEAD:{rel}"],cwd=ROOT,text=True,stderr=subprocess.PIPE)
        return load_text_json(text,{})
    except Exception as exc:
        raise RuntimeError(f"git show failed for HEAD:{rel}") from exc

def event_history_violations(old,new):
    problems=[]
    old_rows={(r.get("event_id"),str(r.get("spec_version")),r.get("score_hash")):r for r in old.get("records") or []}
    new_rows={(r.get("event_id"),str(r.get("spec_version")),r.get("score_hash")):r for r in new.get("records") or []}
    for key,row in old_rows.items():
        if key not in new_rows:problems.append(f"event_history_missing:{key}")
        elif new_rows[key]!=row:problems.append(f"event_history_rewritten:{key}")
    return problems

RULE_IMMUTABLE=("rule_id","semantic_hash","duplicate_rank","first_seen_at","source_id","normalized_rule_hash")
def rule_violations(old,new):
    problems=[]
    old_rows={r.get("rule_id"):r for r in old.get("rules") or [] if r.get("rule_id")}
    new_rows={r.get("rule_id"):r for r in new.get("rules") or [] if r.get("rule_id")}
    for rid,row in old_rows.items():
        nr=new_rows.get(rid)
        if not nr:
            problems.append(f"rule_missing:{rid}");continue
        for k in RULE_IMMUTABLE:
            if nr.get(k)!=row.get(k):problems.append(f"rule_immutable_changed:{rid}:{k}")
        old_hash=row.get("extractor_input_hash")
        if old_hash and nr.get("extractor_input_hash")!=old_hash:
            revisions={x.get("extractor_input_hash") for x in nr.get("extractor_input_revisions") or []}
            if old_hash not in revisions:problems.append(f"rule_extractor_revision_lost:{rid}")
    return problems

def source_observation_violations(old,new):
    problems=[]
    old_rows={str(r.get("source_id")):r for r in old.get("source_observations") or [] if r.get("source_id")}
    new_rows={str(r.get("source_id")):r for r in new.get("source_observations") or [] if r.get("source_id")}
    for sid,row in old_rows.items():
        nr=new_rows.get(sid)
        if not nr:
            problems.append(f"source_observation_missing:{sid}");continue
        for k in ("source_id","first_registry_seen_at","first_extractor_version","first_extractor_input_hash"):
            if nr.get(k)!=row.get(k):
                problems.append(f"source_observation_immutable_changed:{sid}:{k}")
    return problems

def funnel_history_violations(old,new):
    problems=[]
    old_rows={str(r.get("snapshot_id")):r for r in old.get("records") or [] if r.get("snapshot_id")}
    new_rows={str(r.get("snapshot_id")):r for r in new.get("records") or [] if r.get("snapshot_id")}
    for sid,row in old_rows.items():
        if sid not in new_rows:problems.append(f"funnel_history_missing:{sid}")
        elif new_rows[sid]!=row:problems.append(f"funnel_history_rewritten:{sid}")
    return problems

def source_store_violations(old,new):
    problems=[]
    old_rows={r.get("source_key"):r for r in old.get("records") or [] if r.get("source_key")}
    new_rows={r.get("source_key"):r for r in new.get("records") or [] if r.get("source_key")}
    for key,row in old_rows.items():
        nr=new_rows.get(key)
        if not nr:
            problems.append(f"source_missing:{key}");continue
        for k in ("first_fetched_at","ingest_type"):
            if nr.get(k)!=row.get(k):problems.append(f"source_immutable_changed:{key}:{k}")
        # Spec 1.7 permits exactly one migration from legacy rows that did not
        # yet carry admission identity. Once present in HEAD, admission fields
        # are immutable.
        for k in ("admission_class","admission_classified_at","identity_parent_source_key"):
            if k in row and nr.get(k)!=row.get(k):
                problems.append(f"source_immutable_changed:{key}:{k}")
        old_hash=row.get("snapshot_hash")
        if old_hash and nr.get("snapshot_hash")!=old_hash:
            hist=set(nr.get("snapshot_history") or [])
            if old_hash not in hist:problems.append(f"source_snapshot_revision_lost:{key}")
    return problems

def contradiction_violations(old,new):
    problems=[]
    old_rows={r.get("contradiction_id"):r for r in old.get("records") or [] if r.get("contradiction_id")}
    new_rows={r.get("contradiction_id"):r for r in new.get("records") or [] if r.get("contradiction_id")}
    for cid,row in old_rows.items():
        nr=new_rows.get(cid)
        if not nr:problems.append(f"contradiction_missing:{cid}");continue
        if nr.get("first_seen_at")!=row.get("first_seen_at"):
            problems.append(f"contradiction_first_seen_changed:{cid}")
    return problems

def check(old_docs,new_docs):
    return (
      event_history_violations(old_docs.get("event_history",{}),new_docs.get("event_history",{}))
      +rule_violations(old_docs.get("rules",{}),new_docs.get("rules",{}))
      +source_observation_violations(old_docs.get("rules",{}),new_docs.get("rules",{}))
      +source_store_violations(old_docs.get("source_store",{}),new_docs.get("source_store",{}))
      +contradiction_violations(old_docs.get("contradictions",{}),new_docs.get("contradictions",{}))
      +funnel_history_violations(old_docs.get("source_rule_funnel_history",{}),new_docs.get("source_rule_funnel_history",{}))
    )

def main():
    old={name:head_json(path.relative_to(ROOT).as_posix()) for name,path in TARGETS.items()}
    new={name:load(path,{}) for name,path in TARGETS.items()}
    problems=check(old,new)
    print(json.dumps({"version":VERSION,"ok":not problems,"violations":problems[:100]},ensure_ascii=False,indent=2))
    return 0 if not problems else 7

if __name__=="__main__":raise SystemExit(main())
