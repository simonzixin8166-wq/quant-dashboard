#!/usr/bin/env python3
"""V6.15.3 single-source method attribution and claim semantics."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"registry"/"rules.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
READING=ROOT/"docs"/"research"/"source_reading_memory.json"
OUT=ROOT/"research"/"state"/"method_attribution.json"
CLAIMS=ROOT/"research"/"state"/"source_claims.json"
VERSION="6.15.8g"

METHOD_PRIORITY=("Sell Put","LEAPS","趋势确认")
OPERATIONAL_METHOD_NAMES={"仓位与加减仓"}
OFFICIAL_SOURCE_KINDS={"sec","sec_filing","ir","company_ir","official","government","fred"}

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def operation_type(rule):
    actions={str(x).lower() for x in ((rule or {}).get("actions") or [])}
    fields=(rule or {}).get("fields") or {}
    if "sell_put" in actions or fields.get("sell_put_strike") is not None:return "sell_put"
    buy_actions={"buy","add","planned_buy"}
    sell_actions={"trim","trim_half","sell","planned_sell","clear"}
    if actions & buy_actions and actions & sell_actions:return "mixed_buy_sell"
    if actions & sell_actions:return "reduce_or_exit"
    if actions & buy_actions:return "buy_or_add"
    if fields.get("entry_1") is not None or fields.get("entry_2") is not None or fields.get("entry_below") is not None:return "planned_entry"
    if fields.get("exit_line") is not None:return "risk_exit_level"
    return "other"

def normalize_methods(candidates):
    cleaned=[m for m in dict.fromkeys(candidates or []) if m not in OPERATIONAL_METHOD_NAMES]
    primary=None
    for name in METHOD_PRIORITY:
        if name in cleaned:
            primary=name;break
    if primary is None and len(cleaned)==1:
        primary=cleaned[0]
    secondary=[m for m in cleaned if m!=primary]
    return primary,secondary

def claim_semantics(record,prop):
    kind=prop.get("kind")
    ev=prop.get("evidence") or {}
    source_kind=str(record.get("source_kind") or "").lower()
    verified=source_kind in OFFICIAL_SOURCE_KINDS
    if kind=="fact":
        if verified:
            claim_type="verified_fact"
            verification_status="source_verified"
        elif ev.get("field") in {"entry_1","entry_2","entry_below","exit_line","sell_put_strike","target_range"}:
            claim_type="author_stated_plan_level"
            verification_status="unverified"
        elif ev.get("operation_index") is not None:
            claim_type="author_reported_action"
            verification_status="unverified"
        else:
            claim_type="source_claim"
            verification_status="unverified"
    else:
        claim_type=kind
        verification_status="not_applicable"
    return claim_type,verification_status

def build(registry,events,reading):
    rule_by_id={r.get("rule_id"):r for r in registry.get("rules") or []}
    attributed=[]
    for e in events.get("events") or []:
        rule=rule_by_id.get(e.get("rule_id")) or {}
        primary,secondary=normalize_methods(rule.get("method_candidates") or [])
        attributed.append({
            "event_id":e.get("event_id"),
            "rule_id":e.get("rule_id"),
            "primary_method":primary,
            "secondary_tags":secondary,
            "operation_type":operation_type(rule.get("normalized_rule") or {}),
            "method_weight":1.0 if primary else 0.0,
            "scoreable":bool(e.get("scoreable")),
            "spec_version":e.get("spec_version"),
        })
    claims=[]
    for r in reading.get("records") or []:
        for p in r.get("propositions") or []:
            ct,vs=claim_semantics(r,p)
            claims.append({
                "proposition_id":p.get("proposition_id"),
                "source_id":r.get("source_id"),
                "source_kind":r.get("source_kind"),
                "author":r.get("author"),
                "published_at":r.get("published_at"),
                "url":r.get("url"),
                "original_kind":p.get("kind"),
                "claim_type":ct,
                "verification_status":vs,
                "text":p.get("text"),
            })
    now=datetime.now(timezone.utc).isoformat()
    return (
        {
            "version":VERSION,"generated_at":now,"mode":"research_only_single_attribution",
            "counts":{
                "events":len(attributed),
                "with_primary_method":sum(1 for x in attributed if x["primary_method"]),
                "scoreable_with_primary_method":sum(1 for x in attributed if x["scoreable"] and x["primary_method"]),
            },
            "events":attributed,
            "guardrails":[
                "Method attribution is defined here once for V6.15 research.",
                "operation_type is never treated as method performance.",
                "Each event contributes weight 1 to at most one primary method.",
                "Title keywords alone do not establish a primary method."
            ],
        },
        {
            "version":VERSION,"generated_at":now,"counts":{"claims":len(claims),"by_type":dict(Counter(x["claim_type"] for x in claims))},
            "claims":claims,
            "guardrails":[
                "Author-reported actions and plan levels are not displayed or scored as verified facts.",
                "verified_fact requires an official source kind and preserved provenance."
            ],
        }
    )

def main():
    attr,claims=build(load(REGISTRY,{}),load(EVENTS,{}),load(READING,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(attr,ensure_ascii=False,indent=2),encoding="utf-8")
    CLAIMS.write_text(json.dumps(claims,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(attr["counts"],ensure_ascii=False))

if __name__=="__main__":main()
