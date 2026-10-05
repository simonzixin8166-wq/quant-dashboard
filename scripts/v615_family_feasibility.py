#!/usr/bin/env python3
"""Structural Rule Family feasibility audit.

This report is deliberately result-blind. It asks whether the frozen family
definition can plausibly accumulate independent authors and forward evidence.
It never changes family membership, thresholds, Promotion or Planner weights.
"""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/"research"/"registry"/"rules.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"
SOURCE=ROOT/"research"/"store"/"source_store.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"family_feasibility.json"
VERSION="6.15.8g"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(rules,families,source,spec):
    dh=(spec.get("definitions") or {}).get("rule_family_definition_hash")
    rule_map={r.get("rule_id"):r for r in rules.get("rules") or []}
    source_map={}
    for row in source.get("records") or []:
        rec=row.get("record") or {}
        sid=rec.get("id") or row.get("source_key")
        if sid is not None:source_map[str(sid)]=row

    active=[a for a in families.get("assignments") or [] if a.get("active") and a.get("definition_hash")==dh]
    grouped=defaultdict(list)
    for a in active:grouped[a.get("family_id")].append(a)

    threshold=int((spec.get("thresholds") or {}).get("independent_authors_min") or 3)
    rows=[]
    all_authors=set()
    for fid,assignments in sorted(grouped.items()):
        members=[]
        authors=set()
        ingest=Counter()
        first_seen=[]
        for a in assignments:
            r=rule_map.get(a.get("rule_id")) or {}
            author=str(r.get("author") or "unknown")
            authors.add(author);all_authors.add(author)
            src=source_map.get(str(r.get("source_id"))) or {}
            it=str(src.get("ingest_type") or "unknown")
            ingest[it]+=1
            if r.get("first_seen_at"):first_seen.append(r.get("first_seen_at"))
            members.append({
                "rule_id":a.get("rule_id"),"author":author,"source_id":r.get("source_id"),
                "ingest_type":it,"first_seen_at":r.get("first_seen_at"),
            })
        unique_authors=len(authors)
        rows.append({
            "family_id":fid,
            "family_key":assignments[0].get("family_key") or {},
            "member_rules":len(assignments),
            "unique_authors":unique_authors,
            "authors":sorted(authors),
            "authors_needed_for_threshold":max(0,threshold-unique_authors),
            "author_threshold_reached":unique_authors>=threshold,
            "ingest_type_counts":dict(ingest),
            "members":members,
        })

    forward_rules=[]
    for r in rule_map.values():
        if not r.get("active",True):continue
        src=source_map.get(str(r.get("source_id"))) or {}
        if str(src.get("ingest_type") or "") not in {"initial_migration","backfill_ingest"}:
            forward_rules.append(r)

    firsts=sorted(str(r.get("first_seen_at")) for r in forward_rules if r.get("first_seen_at"))
    longitudinal_days=0
    if len(firsts)>=2:
        try:
            a=datetime.fromisoformat(firsts[0].replace("Z","+00:00"))
            b=datetime.fromisoformat(firsts[-1].replace("Z","+00:00"))
            longitudinal_days=max(0,(b-a).days)
        except Exception:pass

    rate_status="insufficient_forward_history"
    weekly_forward_rule_rate=None
    if len(forward_rules)>=2 and longitudinal_days>=14:
        weekly_forward_rule_rate=len(forward_rules)/(longitudinal_days/7.0)
        rate_status="estimable"

    max_authors=max((x["unique_authors"] for x in rows),default=0)
    families_at_threshold=sum(1 for x in rows if x["author_threshold_reached"])
    singleton_author_families=sum(1 for x in rows if x["unique_authors"]==1)

    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "family_definition_hash":dh,
        "result_blind":True,
        "counts":{
            "active_families":len(rows),
            "active_rules":len(active),
            "unique_authors_across_active_rules":len(all_authors),
            "families_meeting_author_threshold":families_at_threshold,
            "single_author_families":singleton_author_families,
            "max_unique_authors_in_one_family":max_authors,
            "forward_rules_observed":len(forward_rules),
        },
        "author_threshold":threshold,
        "forward_rule_rate":{
            "status":rate_status,
            "longitudinal_days":longitudinal_days,
            "weekly_forward_rule_rate":weekly_forward_rule_rate,
            "minimum_history_before_rate_estimate_days":14,
            "note":"Migration/backfill rules are excluded from forward intake-rate estimation."
        },
        "families":rows,
        "assessment":{
            "current_author_diversity_sufficient":families_at_threshold>0,
            "family_granularity_review_needed_now":False,
            "reason":"No family yet has forward longitudinal evidence sufficient to estimate cross-author convergence. Do not coarsen families using outcome or pass-rate information.",
            "next_structural_review_trigger":"At least 28 calendar days of forward rule intake and at least 3 distinct forward authors across active rules.",
        },
        "guardrails":[
            "This report does not use returns, win rates, lift, MAE, FDR outcomes or Promotion results.",
            "Backfill/migration rules do not estimate future rule generation velocity.",
            "A coarse-family alternative may be designed only from structural features and must be frozen before inspecting its performance.",
            "This report cannot change family membership or Evaluation Spec automatically."
        ],
    }

def main():
    out=build(load(RULES,{}),load(FAMILIES,{}),load(SOURCE,{}),load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
