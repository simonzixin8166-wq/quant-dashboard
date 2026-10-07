#!/usr/bin/env python3
"""Candidate Rule Compiler v1.0.

Compiles prose-derived Source Reading candidate_rule propositions into an
explicit Research/Shadow registry. This module is intentionally non-production:
it cannot write the protected Rule Registry, Promotion Gate, positions, sizing,
or orders.

Design goals:
- preserve exact source/proposition provenance;
- compile only already-extracted source-derived conditions;
- never invent indicator formulas, thresholds or horizons;
- keep unsupported inputs (for example an undefined TCDS formula) unresolved;
- distinguish historical/backfill from genuine-forward observation eligibility.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
READING=ROOT/"docs"/"research"/"source_reading_memory.json"
STORE=ROOT/"research"/"store"/"source_store.json"
REGISTRY=ROOT/"research"/"registry"/"candidate_rules.json"
STATUS=ROOT/"docs"/"research"/"candidate_rule_status.json"
VERSION="1.0"

MACHINE_CONDITIONS={
    "price_above_ma50":{"indicator":"price_vs_ma50","operator":"above","threshold":"MA50"},
    "price_below_ma50":{"indicator":"price_vs_ma50","operator":"below","threshold":"MA50"},
    "ma50_hold_two_sessions":{"indicator":"price_vs_ma50","operator":"hold_above","sessions":2},
    "supertrend_bullish":{"indicator":"supertrend","operator":"bullish"},
    "macd_hist_positive":{"indicator":"macd_histogram","operator":"positive"},
}
UNRESOLVED_KNOWN={
    "ppo_above_signal":"PPO periods/definition not verified",
    "ppo_hist_positive":"PPO periods/definition not verified",
    "tcds_cross_zero":"TCDS formula/parameters not defined in source",
}
STATE_TO_ROLE={
    "EARLY_ENTRY":"trigger",
    "CONFIRMATION":"confirmation",
    "RISK":"invalidation_or_risk",
}

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def stable_id(*parts):
    raw="|".join(str(x or "") for x in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]

def store_index(store):
    out={}
    for row in store.get("records") or []:
        rec=(row or {}).get("record") or {}
        sid=str(rec.get("id") or row.get("source_key") or "")
        if sid:out[sid]=row
    return out

def evidence_role(store_row):
    cls=(store_row or {}).get("admission_class")
    high=(store_row or {}).get("timestamp_confidence")=="high"
    if cls=="genuine_forward" and high:
        return "genuine_forward_observation"
    if cls in {"backfill","late_discovery","identity_ambiguous","rekeyed_duplicate","initial_migration"}:
        return "historical_or_nonforward"
    return "historical_or_nonforward"

def compile_condition(item):
    cid=str((item or {}).get("condition_id") or "")
    if cid in MACHINE_CONDITIONS:
        return {"condition_id":cid,"machine_ready":True,"expression":MACHINE_CONDITIONS[cid],"unresolved_reason":None}
    reason=UNRESOLVED_KNOWN.get(cid,"Condition definition is not machine-reproducible")
    return {"condition_id":cid,"machine_ready":False,"expression":None,"unresolved_reason":reason}

def infer_family(compiled):
    ids={x["condition_id"] for x in compiled}
    if any(x.startswith("tcds_") or x.startswith("ppo_") for x in ids):
        return "trend_confirmation"
    if any("ma50" in x or x.startswith("supertrend") or x.startswith("macd") for x in ids):
        return "trend_confirmation"
    return "unclassified_method"

def compile_candidate(memory,prop,store_row):
    ev=(prop.get("evidence") or {}).get("candidate_rule") or {}
    conditions=[compile_condition(x) for x in (ev.get("conditions") or []) if isinstance(x,dict)]
    if not conditions:return None
    unresolved=[x for x in conditions if not x["machine_ready"]]
    ready=[x for x in conditions if x["machine_ready"]]
    role=evidence_role(store_row)
    forward_observation_eligible=(role=="genuine_forward_observation" and not unresolved and bool(ready))
    status="machine_ready_shadow" if ready and not unresolved else "partial_needs_definition"
    if not ready:status="blocked_needs_definition"
    sid=str(memory.get("source_id") or "")
    pid=str(prop.get("proposition_id") or "")
    return {
        "candidate_id":"cand_"+stable_id(VERSION,sid,pid),
        "compiler_version":VERSION,
        "source_id":sid,
        "proposition_id":pid,
        "source":{
            "author":memory.get("author"),
            "source":memory.get("source"),
            "source_kind":memory.get("source_kind"),
            "published_at":memory.get("published_at"),
            "title":memory.get("title"),
            "url":memory.get("url"),
            "content_quality":memory.get("content_quality"),
        },
        "scope":{"symbols":list(ev.get("symbols") or memory.get("symbols") or [])},
        "method_family":infer_family(conditions),
        "state_hint":ev.get("state_hint"),
        "state_role":STATE_TO_ROLE.get(str(ev.get("state_hint") or ""),"unspecified"),
        "conditions":conditions,
        "machine_ready_conditions":[x["condition_id"] for x in ready],
        "unresolved_inputs":[{"condition_id":x["condition_id"],"reason":x["unresolved_reason"]} for x in unresolved],
        "reproducibility_status":status,
        "evidence_role":role,
        "forward_observation_eligible":forward_observation_eligible,
        "historical_replay_eligible":bool(ready),
        "production_eligible":False,
        "promotion_eligible":False,
        "horizon":"unknown_until_explicitly_defined",
        "raw_evidence":list(ev.get("raw_evidence") or [])[:6],
        "guardrails":[
            "Research/Shadow only.",
            "No missing formula, parameter, threshold or horizon is inferred.",
            "Backfill/historical evidence cannot become Forward evidence by relabeling.",
            "This candidate cannot alter protected production rules or place trades.",
        ],
    }

def build(reading,store):
    idx=store_index(store)
    rows=[]
    for memory in reading.get("records") or []:
        sid=str(memory.get("source_id") or "")
        for prop in memory.get("propositions") or []:
            if prop.get("kind")!="candidate_rule":continue
            c=compile_candidate(memory,prop,idx.get(sid))
            if c:rows.append(c)
    rows=sorted(rows,key=lambda x:x["candidate_id"])
    counts=Counter(x["reproducibility_status"] for x in rows)
    fam=Counter(x["method_family"] for x in rows)
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"research_shadow_only",
        "counts":{
            "candidates":len(rows),
            "machine_ready_shadow":counts["machine_ready_shadow"],
            "partial_needs_definition":counts["partial_needs_definition"],
            "blocked_needs_definition":counts["blocked_needs_definition"],
            "historical_replay_eligible":sum(1 for x in rows if x["historical_replay_eligible"]),
            "forward_observation_eligible":sum(1 for x in rows if x["forward_observation_eligible"]),
            "production_eligible":0,
        },
        "by_family":dict(fam),
        "candidates":rows,
        "guardrails":[
            "Candidate Rule Compiler writes only the Research/Shadow candidate registry.",
            "It never writes research/registry/rules.json or Promotion Gate outputs.",
            "Undefined source-specific indicators remain unresolved.",
            "Forward observation eligibility requires genuine_forward plus high timestamp confidence and a fully reproducible candidate.",
            "Production eligibility is always false in this compiler.",
        ],
    }

def public_status(reg):
    samples=[]
    for x in reg.get("candidates") or []:
        samples.append({
            "candidate_id":x["candidate_id"],
            "author":x["source"].get("author"),
            "title":x["source"].get("title"),
            "symbols":x["scope"].get("symbols"),
            "method_family":x["method_family"],
            "reproducibility_status":x["reproducibility_status"],
            "unresolved_inputs":x["unresolved_inputs"],
            "evidence_role":x["evidence_role"],
            "forward_observation_eligible":x["forward_observation_eligible"],
            "production_eligible":False,
        })
    return {
        "version":reg.get("version"),
        "generated_at":reg.get("generated_at"),
        "counts":reg.get("counts"),
        "by_family":reg.get("by_family"),
        "sample":samples[:40],
        "production_effect":"none",
        "guardrails":reg.get("guardrails"),
    }

def main():
    reg=build(load(READING,{"records":[]}),load(STORE,{"records":[]}))
    REGISTRY.parent.mkdir(parents=True,exist_ok=True)
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    REGISTRY.write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    STATUS.write_text(json.dumps(public_status(reg),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(reg["counts"],ensure_ascii=False))

if __name__=="__main__":main()
