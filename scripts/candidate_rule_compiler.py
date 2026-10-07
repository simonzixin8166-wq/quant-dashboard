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
    "price_above_ma20":{"indicator":"price_vs_ma20","operator":"above","threshold":"MA20"},
    "price_below_ma20":{"indicator":"price_vs_ma20","operator":"below","threshold":"MA20"},
    "ma20_hold_two_sessions":{"indicator":"price_vs_ma20","operator":"hold_above","sessions":2},
    "price_above_ma50":{"indicator":"price_vs_ma50","operator":"above","threshold":"MA50"},
    "price_below_ma50":{"indicator":"price_vs_ma50","operator":"below","threshold":"MA50"},
    "ma50_hold_two_sessions":{"indicator":"price_vs_ma50","operator":"hold_above","sessions":2},
    "price_above_ma200":{"indicator":"price_vs_ma200","operator":"above","threshold":"MA200"},
    "price_below_ma200":{"indicator":"price_vs_ma200","operator":"below","threshold":"MA200"},
    "ma200_hold_two_sessions":{"indicator":"price_vs_ma200","operator":"hold_above","sessions":2},
}
UNRESOLVED_KNOWN={
    "supertrend_bullish":"Supertrend ATR period/multiplier not verified",
    "macd_hist_positive":"MACD fast/slow/signal periods not verified",
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
    role=str((item or {}).get("semantic_role") or "unspecified")
    if cid in MACHINE_CONDITIONS:
        return {"condition_id":cid,"semantic_role":role,"machine_ready":True,"expression":MACHINE_CONDITIONS[cid],"unresolved_reason":None}
    reason=UNRESOLVED_KNOWN.get(cid,"Condition definition is not machine-reproducible")
    return {"condition_id":cid,"semantic_role":role,"machine_ready":False,"expression":None,"unresolved_reason":reason}

def infer_family(compiled):
    ids={x["condition_id"] for x in compiled}
    if any(x.startswith("tcds_") or x.startswith("ppo_") for x in ids):
        return "trend_confirmation"
    if any(("ma20" in x or "ma50" in x or "ma200" in x) or x.startswith("supertrend") or x.startswith("macd") for x in ids):
        return "trend_confirmation"
    return "unclassified_method"

def compile_candidate(memory,prop,store_row,forward_formation_allowed=False):
    ev=(prop.get("evidence") or {}).get("candidate_rule") or {}
    conditions=[compile_condition(x) for x in (ev.get("conditions") or []) if isinstance(x,dict)]
    if not conditions:return None
    unresolved=[x for x in conditions if not x["machine_ready"]]
    ready=[x for x in conditions if x["machine_ready"]]
    semantic_roles={x.get("semantic_role") for x in conditions if x.get("semantic_role") not in {None,"unspecified"}}
    temporal_unresolved=None
    if "prior_observation" in semantic_roles and "invalidation" in semantic_roles:
        temporal_unresolved={
            "condition_id":"temporal_sequence_window",
            "reason":"Source describes a prior-state -> invalidation transition but does not define an exact replay lookback/window."
        }
    role=evidence_role(store_row)
    status="machine_ready_shadow" if ready and not unresolved and temporal_unresolved is None else "partial_needs_definition"
    if not ready:status="blocked_needs_definition"
    forward_observation_eligible=(role=="genuine_forward_observation" and forward_formation_allowed and status=="machine_ready_shadow")
    sid=str(memory.get("source_id") or "")
    pid=str(prop.get("proposition_id") or "")
    family=infer_family(conditions)
    state_role=STATE_TO_ROLE.get(str(ev.get("state_hint") or ""),"unspecified")
    explicit_roles=any(x.get("semantic_role") not in {None,"unspecified"} for x in conditions)
    if explicit_roles:
        logic={
            "prior_observation_conditions":[x["condition_id"] for x in conditions if x.get("semantic_role")=="prior_observation"],
            "trigger_conditions":[x["condition_id"] for x in conditions if x.get("semantic_role")=="trigger"],
            "confirmation_conditions":[x["condition_id"] for x in conditions if x.get("semantic_role")=="confirmation"],
            "invalidation_conditions":[x["condition_id"] for x in conditions if x.get("semantic_role")=="invalidation"],
        }
    else:
        logic={
            "prior_observation_conditions":[],
            "trigger_conditions":[x["condition_id"] for x in conditions] if state_role=="trigger" else [],
            "confirmation_conditions":[x["condition_id"] for x in conditions] if state_role=="confirmation" else [],
            "invalidation_conditions":[x["condition_id"] for x in conditions] if state_role=="invalidation_or_risk" else [],
        }
    family_signature=stable_id(
        family,state_role,
        ",".join(sorted(x["condition_id"] for x in conditions)),
        "horizon:unknown"
    )
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
        "scope":{"symbols":list(ev.get("symbols") or memory.get("symbols") or []),"subject_attribution":"single_symbol_source_scope"},
        "method_family":family,
        "family_signature":"family_"+family_signature,
        "state_hint":ev.get("state_hint"),
        "state_role":state_role,
        "logic":logic,
        "conditions":conditions,
        "machine_ready_conditions":[x["condition_id"] for x in ready],
        "unresolved_inputs":[{"condition_id":x["condition_id"],"reason":x["unresolved_reason"]} for x in unresolved] + ([temporal_unresolved] if temporal_unresolved else []),
        "reproducibility_status":status,
        "evidence_role":role,
        "forward_observation_eligible":forward_observation_eligible,
        "historical_replay_eligible":status=="machine_ready_shadow",
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

def build(reading,store,prior=None,now=None):
    """Compile candidates with a source-observation lock.

    A source can create a Forward-observation-eligible candidate only on the
    first compiler observation of that source, after the observation feature
    already exists. This prevents a later parser improvement from converting
    an already-seen source into hindsight Forward evidence.
    """
    now=now or datetime.now(timezone.utc).isoformat()
    prior=prior or {}
    idx=store_index(store)
    prior_obs={str(x.get("source_id")):x for x in (prior.get("source_observations") or []) if x.get("source_id")}
    observation_feature_preexisting="source_observations" in prior
    observations=[]
    seen=set()
    rows=[]
    for memory in reading.get("records") or []:
        sid=str(memory.get("source_id") or "")
        if not sid:continue
        old_obs=prior_obs.get(sid)
        meta=idx.get(sid) or {}
        seen.add(sid)
        observations.append({
            "source_id":sid,
            "first_candidate_compiler_seen_at":(old_obs or {}).get("first_candidate_compiler_seen_at") or now,
            "last_candidate_compiler_seen_at":now,
            "source_admission_class":meta.get("admission_class"),
            "source_first_fetched_at":meta.get("first_fetched_at"),
        })
        forward_formation_allowed=(
            observation_feature_preexisting
            and old_obs is None
            and evidence_role(meta)=="genuine_forward_observation"
        )
        for prop in memory.get("propositions") or []:
            if prop.get("kind")!="candidate_rule":continue
            candidate=compile_candidate(memory,prop,meta,forward_formation_allowed)
            if candidate:
                candidate["formation_mode"]=(
                    "forward_initial" if candidate["forward_observation_eligible"]
                    else ("migration_baseline" if not observation_feature_preexisting else "historical_or_retroactive")
                )
                rows.append(candidate)
    for sid,old_obs in prior_obs.items():
        if sid not in seen:observations.append(dict(old_obs))
    rows=sorted(rows,key=lambda x:x["candidate_id"])
    observations=sorted(observations,key=lambda x:x["source_id"])
    counts=Counter(x["reproducibility_status"] for x in rows)
    fam=Counter(x["method_family"] for x in rows)
    return {
        "version":VERSION,
        "generated_at":now,
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
        "capabilities":{
            "machine_conditions":sorted(MACHINE_CONDITIONS.keys()),
            "generic_moving_average_windows":[20,50,200],
            "generic_moving_average_support_complete":all(
                key in MACHINE_CONDITIONS for key in (
                    "price_above_ma20","price_below_ma20","ma20_hold_two_sessions",
                    "price_above_ma50","price_below_ma50","ma50_hold_two_sessions",
                    "price_above_ma200","price_below_ma200","ma200_hold_two_sessions",
                )
            ),
            "parameterized_indicators_fail_closed":sorted(UNRESOLVED_KNOWN.keys()),
        },
        "source_observations":observations,
        "candidates":rows,
        "guardrails":[
            "Candidate Rule Compiler writes only the Research/Shadow candidate registry.",
            "It never writes research/registry/rules.json or Promotion Gate outputs.",
            "Undefined source-specific indicators remain unresolved.",
            "Forward observation eligibility requires genuine_forward, high timestamp confidence, full reproducibility, and candidate formation on the source's first compiler observation.",
            "Already-seen sources cannot become Forward evidence because of later extraction improvements.",
            "The first migration cycle is non-forward by construction.",
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
        "capabilities":reg.get("capabilities") or {},
        "sample":samples[:40],
        "production_effect":"none",
        "guardrails":reg.get("guardrails"),
    }

def main():
    prior=load(REGISTRY,{})
    reg=build(load(READING,{"records":[]}),load(STORE,{"records":[]}),prior=prior)
    REGISTRY.parent.mkdir(parents=True,exist_ok=True)
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    REGISTRY.write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    STATUS.write_text(json.dumps(public_status(reg),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(reg["counts"],ensure_ascii=False))

if __name__=="__main__":main()
