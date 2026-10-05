#!/usr/bin/env python3
"""V6.15.8g structural-only Family feasibility and Readiness reachability audit.

This module never reads realized returns, scorecards, confidence intervals,
Promotion pass/fail or named-method performance. It measures only whether the
frozen structural taxonomy can plausibly accumulate independent evidence.
"""
from __future__ import annotations
import hashlib,json,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/"research"/"registry"/"rules.json"
DEFN=ROOT/"research"/"specs"/"rule_family_definition.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
READINESS_SPEC=ROOT/"research"/"specs"/"v616_readiness_spec.json"
SOURCE_STORE=ROOT/"research"/"store"/"source_store.json"
OUT=ROOT/"research"/"audit"/"family_feasibility.json"
VERSION="6.15.8g"

sys.path.insert(0,str(ROOT/"scripts"))
from v615_rule_family import structural_key

PROSPECTIVE_INGEST_TYPES={"prospective","incremental","live_incremental","daily_incremental","post_freeze_incremental"}

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def fid(level,key):
    return "diag_"+level+"_"+hashlib.sha256(canonical(key).encode("utf-8")).hexdigest()[:20]

def source_provenance(store):
    out={}
    for row in store.get("records") or []:
        rec=row.get("record") or {}
        sid=str(rec.get("id") or row.get("source_key") or "")
        if sid:
            out[sid]={
                "ingest_type":row.get("ingest_type"),
                "first_fetched_at":row.get("first_fetched_at"),
                "author":rec.get("author"),
            }
    return out

def parse_dt(value):
    try:return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:return None

def level_summary(rules,defn,level):
    dims=level.get("dimensions") or []
    groups=defaultdict(list)
    for r in rules.get("rules") or []:
        if not r.get("active",True):continue
        full=structural_key(r,defn)
        key={k:full.get(k) for k in dims}
        groups[fid(level.get("level") or "unknown",key)].append(r)
    rows=[]
    for family_id,members in sorted(groups.items()):
        authors=sorted({str(x.get("author") or "unknown") for x in members})
        rows.append({
            "family_id":family_id,
            "member_rules":len(members),
            "independent_authors":len(authors),
            "authors":authors,
        })
    fam_n=len(rows)
    singleton=sum(1 for x in rows if x["member_rules"]==1)
    return {
        "level":level.get("level"),
        "activation":level.get("activation"),
        "dimensions":dims,
        "active_rules":sum(x["member_rules"] for x in rows),
        "families":fam_n,
        "singleton_families":singleton,
        "singleton_share":None if fam_n==0 else singleton/fam_n,
        "families_with_2plus_authors":sum(1 for x in rows if x["independent_authors"]>=2),
        "families_with_3plus_authors":sum(1 for x in rows if x["independent_authors"]>=3),
        "max_independent_authors":max([x["independent_authors"] for x in rows] or [0]),
        "families_detail":rows,
    }

def prospective_rules(rules,store):
    prov=source_provenance(store)
    out=[]
    for r in rules.get("rules") or []:
        if not r.get("active",True):continue
        p=prov.get(str(r.get("source_id"))) or {}
        if str(p.get("ingest_type") or "") not in PROSPECTIVE_INGEST_TYPES:
            continue
        dt=parse_dt(p.get("first_fetched_at") or r.get("first_seen_at"))
        if dt:
            out.append({"rule_id":r.get("rule_id"),"author":r.get("author"),"seen_at":dt})
    return out

def rate_estimate(rows):
    if len(rows)<2:
        return {"status":"not_estimable","prospective_rules":len(rows),"reason":"fewer_than_2_prospective_rules"}
    dates=sorted(x["seen_at"] for x in rows)
    span=max(0.0,(dates[-1]-dates[0]).total_seconds()/86400.0)
    distinct=len({x.date().isoformat() for x in dates})
    if span<14 or distinct<2:
        return {
            "status":"not_estimable","prospective_rules":len(rows),
            "span_days":round(span,2),"distinct_days":distinct,
            "reason":"prospective_observation_span_under_14_days",
        }
    return {
        "status":"estimable_descriptive_only",
        "prospective_rules":len(rows),"span_days":round(span,2),"distinct_days":distinct,
        "rules_per_30_calendar_days":round(len(rows)/span*30.0,3),
    }

def build(rules,defn,spec,readiness,store):
    ladder=(defn.get("coarsening_ladder") or {}).get("levels") or []
    levels=[level_summary(rules,defn,x) for x in ladder]
    prospective=prospective_rules(rules,store)
    rate=rate_estimate(prospective)
    req=(readiness.get("requirements") or {})
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "family_definition_version":defn.get("definition_version"),
        "family_definition_hash":defn.get("definition_hash"),
        "mode":"structural_only_result_blind",
        "levels":levels,
        "prospective_generation_rate":rate,
        "readiness_requirements_snapshot":{
            "point_in_time_mature_20_effective_units_min":req.get("point_in_time_mature_20_effective_units_min"),
            "point_in_time_mature_60_effective_units_min":req.get("point_in_time_mature_60_effective_units_min"),
            "families_with_mature_20_min":req.get("families_with_mature_20_min"),
            "families_with_mature_60_min":req.get("families_with_mature_60_min"),
        },
        "assessment":{
            "active_level":(spec.get("definitions") or {}).get("family_feasibility",{}).get("active_level"),
            "coarser_levels_are_diagnostic_only":True,
            "rate_estimate_status":rate.get("status"),
            "do_not_activate_coarser_family_from_this_report":True,
        },
        "guardrails":[
            "This report never reads returns, scorecards, CI, FDR, Promotion results or method pass/fail.",
            "Existing migrated rules are not used to fabricate a prospective generation rate.",
            "A coarser family level remains diagnostic-only until a future reviewed definition/spec version explicitly activates it.",
            "Family thresholds and independent-author requirements are unchanged."
        ],
    }

def main():
    out=build(load(RULES,{}),load(DEFN,{}),load(SPEC,{}),load(READINESS_SPEC,{}),load(SOURCE_STORE,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "spec_version":out["spec_version"],
        "levels":[{k:x[k] for k in ("level","families","singleton_families","families_with_3plus_authors","max_independent_authors")} for x in out["levels"]],
        "prospective_generation_rate":out["prospective_generation_rate"],
    },ensure_ascii=False))

if __name__=="__main__":main()
