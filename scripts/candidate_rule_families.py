#!/usr/bin/env python3
"""Candidate Rule Family aggregator v1.0.

Groups Research/Shadow candidates by deterministic family_signature so later
validation compares method families rather than isolated posts or authors.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"research"/"registry"/"candidate_rules.json"
REPLAY=ROOT/"docs"/"research"/"candidate_rule_replay.json"
OUT=ROOT/"research"/"registry"/"candidate_rule_families.json"
PUBLIC=ROOT/"docs"/"research"/"candidate_rule_family_status.json"
VERSION="1.0"

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def build(registry,replay):
    replay_by={x.get("candidate_id"):x for x in replay.get("candidates") or []}
    groups={}
    for c in registry.get("candidates") or []:
        fid=str(c.get("family_signature") or "")
        if not fid:continue
        g=groups.setdefault(fid,{
            "family_id":fid,
            "method_family":c.get("method_family"),
            "state_role":c.get("state_role"),
            "candidate_ids":[],
            "authors":set(),
            "symbols":set(),
            "unresolved_inputs":set(),
            "machine_ready_candidates":0,
            "forward_observation_candidates":0,
            "historically_replayed_candidates":0,
            "historical_raw_events":0,
            "historical_effective_clusters":0,
        })
        g["candidate_ids"].append(c.get("candidate_id"))
        a=(c.get("source") or {}).get("author")
        if a:g["authors"].add(str(a))
        for s in (c.get("scope") or {}).get("symbols") or []:g["symbols"].add(str(s))
        for x in c.get("unresolved_inputs") or []:
            g["unresolved_inputs"].add(str(x.get("condition_id") or ""))
        if c.get("reproducibility_status")=="machine_ready_shadow":g["machine_ready_candidates"]+=1
        if c.get("forward_observation_eligible"):g["forward_observation_candidates"]+=1
        rr=replay_by.get(c.get("candidate_id")) or {}
        if rr.get("status")=="replayed":
            g["historically_replayed_candidates"]+=1
            g["historical_raw_events"]+=int(rr.get("raw_events") or 0)
            g["historical_effective_clusters"]+=int(rr.get("effective_clusters") or 0)
    rows=[]
    for g in groups.values():
        g["authors"]=sorted(g["authors"])
        g["symbols"]=sorted(g["symbols"])
        g["unresolved_inputs"]=sorted(x for x in g["unresolved_inputs"] if x)
        g["independent_authors"]=len(g["authors"])
        g["candidate_count"]=len(g["candidate_ids"])
        g["state"]="shadow_replay_ready" if g["machine_ready_candidates"] else "needs_definition"
        g["promotion_eligible"]=False
        g["production_eligible"]=False
        rows.append(g)
    rows.sort(key=lambda x:(-x["machine_ready_candidates"],-x["independent_authors"],x["family_id"]))
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"research_shadow_family_registry",
        "counts":{
            "families":len(rows),
            "shadow_replay_ready":sum(1 for x in rows if x["state"]=="shadow_replay_ready"),
            "needs_definition":sum(1 for x in rows if x["state"]=="needs_definition"),
            "multi_author_families":sum(1 for x in rows if x["independent_authors"]>=2),
            "promotion_eligible":0,
            "production_eligible":0,
        },
        "families":rows,
        "guardrails":[
            "Family aggregation is descriptive Research/Shadow state only.",
            "Independent authors do not by themselves establish validity.",
            "Historical replay does not establish Forward maturity.",
            "No family is Promotion- or Production-eligible in this module.",
        ],
    }

def public(reg):
    return {
        "version":reg.get("version"),"generated_at":reg.get("generated_at"),
        "counts":reg.get("counts"),"families":[{
            "family_id":x.get("family_id"),"method_family":x.get("method_family"),
            "state_role":x.get("state_role"),"candidate_count":x.get("candidate_count"),
            "independent_authors":x.get("independent_authors"),"symbols":x.get("symbols"),
            "state":x.get("state"),"unresolved_inputs":x.get("unresolved_inputs"),
            "historical_raw_events":x.get("historical_raw_events"),
            "historical_effective_clusters":x.get("historical_effective_clusters"),
            "production_eligible":False,
        } for x in reg.get("families") or []][:40],
        "production_effect":"none",
    }

def main():
    out=build(load(SRC,{"candidates":[]}),load(REPLAY,{"candidates":[]}))
    OUT.parent.mkdir(parents=True,exist_ok=True);PUBLIC.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PUBLIC.write_text(json.dumps(public(out),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
