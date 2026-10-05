#!/usr/bin/env python3
"""V6.15.8b immutable, result-blind Rule Family registry."""
from __future__ import annotations
import hashlib,json,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/"research"/"registry"/"rules.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
DEF=ROOT/"research"/"specs"/"rule_family_definition.json"
OUT=ROOT/"research"/"registry"/"rule_families.json"
VERSION="6.15.8i"

sys.path.insert(0,str(ROOT/"scripts"))
from entry_semantics import classify_rule
from v615_method_attribution import operation_type,normalize_methods

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def sha(v):
    return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def verify_definition(defn):
    body={k:v for k,v in defn.items() if k not in {"definition_hash","guardrails"}}
    # definition_hash was frozen over the core definition fields only.
    core={
      "definition_version":defn.get("definition_version"),
      "normalizer_version":defn.get("normalizer_version"),
      "extractor_version":defn.get("extractor_version"),
      "immutable_dimensions":defn.get("immutable_dimensions"),
      "rule_template":defn.get("rule_template"),
      "condition_classes":defn.get("condition_classes"),
      "instrument_type_rules":defn.get("instrument_type_rules"),
      "direction_rules":defn.get("direction_rules"),
      "assignment_policy":defn.get("assignment_policy"),
    }
    got=sha(core)
    expected=defn.get("definition_hash")
    if got!=expected:
        raise ValueError(f"rule family definition hash mismatch: {got} != {expected}")
    return got

def condition_classes(rule,defn):
    text=" ".join(str(x).lower() for x in ((rule or {}).get("conditions") or []))
    out=[]
    classes=defn.get("condition_classes") or {}
    for name,words in classes.items():
        if name=="other":continue
        if any(str(w).lower() in text for w in words or []):
            out.append(name)
    return sorted(out or ["other"])

def primary_method(rule):
    primary,_=normalize_methods(rule.get("method_candidates") or [])
    return primary or "unattributed"

def structural_direction(rule,method,defn=None):
    nr=rule.get("normalized_rule") or {}
    actions={str(x).lower() for x in (nr.get("actions") or [])}
    if method=="Sell Put":return "option_bullish_income"
    if method=="LEAPS":return "option_bullish"
    cfg=(defn or {}).get("direction_rules") or {}
    option_actions=set(str(x).lower() for x in (cfg.get("option_context_action_tokens") or []))
    option_fields=set(str(x).lower() for x in (cfg.get("option_context_field_tokens") or []))
    fields={str(x).lower() for x in ((nr.get("fields") or {}).keys())}
    field_has_option_context=any(any(tok in field for tok in option_fields) for field in fields)
    # Unsupported option structures (e.g. covered-call-like generic sell + call fields)
    # must fail closed instead of being mislabeled as a bearish stock exit.
    if (actions & option_actions) or field_has_option_context:
        return "unknown"
    bullish=set(str(x).lower() for x in (cfg.get("bullish_actions") or ["buy","add","planned_buy"]))
    bearish=set(str(x).lower() for x in (cfg.get("bearish_actions") or ["sell","planned_sell","clear","trim","trim_half","reduce"]))
    has_bull=bool(actions & bullish)
    has_bear=bool(actions & bearish)
    if has_bull and has_bear:
        return cfg.get("mixed_direction_label") or "mixed_direction"
    if has_bull:return "bullish"
    if has_bear:return "bearish"
    return "unknown"

def instrument_type(rule,method,defn):
    cfg=defn.get("instrument_type_rules") or {}
    if method in set(cfg.get("option_structure_methods") or []):
        return "option_structure"
    etfs=set(cfg.get("etf_symbols") or [])
    symbols=set(rule.get("symbols") or [])
    if symbols and symbols<=etfs:return "etf"
    if symbols and symbols & etfs and symbols-etfs:return "mixed"
    return cfg.get("fallback") or "equity"

def template(rule,defn):
    nr=rule.get("normalized_rule") or {}
    fields=nr.get("fields") or {}
    return {
        "field_names":sorted(str(k) for k,v in fields.items() if v is not None),
        "actions":sorted(str(x).lower() for x in (nr.get("actions") or [])),
        "condition_classes":condition_classes(nr,defn),
    }

def structural_key(rule,defn):
    method=primary_method(rule)
    nr=rule.get("normalized_rule") or {}
    return {
        "primary_method":method,
        "operation_type":operation_type(nr),
        "entry_semantic":classify_rule(nr),
        "direction":structural_direction(rule,method,defn),
        "instrument_type":instrument_type(rule,method,defn),
        "rule_template":template(rule,defn),
    }

def build(rules,spec,defn,prior=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    dh=verify_definition(defn)
    expected=((spec.get("definitions") or {}).get("rule_family_definition_hash"))
    if expected!=dh:
        raise ValueError("evaluation spec family definition hash does not match frozen definition")
    version=defn.get("definition_version")
    prior_rows=list((prior or {}).get("assignments") or [])
    prior_key={(x.get("rule_id"),x.get("definition_hash")):x for x in prior_rows}
    current=[]
    for rule in rules.get("rules") or []:
        if not rule.get("active",True) or rule.get("forward_eligible") is False:continue
        key=structural_key(rule,defn)
        fid="family_"+hashlib.sha256(f"{dh}|{canonical(key)}".encode("utf-8")).hexdigest()[:24]
        old=prior_key.get((rule.get("rule_id"),dh))
        if old and old.get("family_id")!=fid:
            raise ValueError(f"immutable family assignment changed for {rule.get('rule_id')}")
        current.append({
            "rule_id":rule.get("rule_id"),
            "family_id":fid,
            "definition_version":version,
            "definition_hash":dh,
            "family_key":key,
            "first_assigned_at":(old or {}).get("first_assigned_at") or now,
            "last_seen_at":now,
            "active":True,
        })
    existing={(x.get("rule_id"),x.get("definition_hash")) for x in prior_rows}
    all_rows=list(prior_rows)
    for x in current:
        k=(x["rule_id"],x["definition_hash"])
        if k in existing:
            for i,row in enumerate(all_rows):
                if (row.get("rule_id"),row.get("definition_hash"))==k:
                    all_rows[i]=x;break
        else:
            all_rows.append(x)
    families=defaultdict(list)
    for x in current:families[x["family_id"]].append(x["rule_id"])
    return {
        "version":VERSION,
        "generated_at":now,
        "spec_version":spec.get("spec_version"),
        "definition_version":version,
        "definition_hash":dh,
        "counts":{"assignments":len(all_rows),"active_assignments":len(current),"active_families":len(families)},
        "assignments":all_rows,
        "families":[{"family_id":fid,"rule_ids":sorted(ids),"member_rules":len(ids)} for fid,ids in sorted(families.items())],
        "guardrails":[
            "Family assignment is result-blind, author-blind and time-blind.",
            "Numeric price levels and realized outcomes are excluded from family identity.",
            "Membership under the same definition hash is immutable.",
            "A new family definition creates a new version instead of rewriting old membership."
        ],
    }

def main():
    out=build(load(RULES,{}),load(SPEC,{}),load(DEF,{}),load(OUT,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
