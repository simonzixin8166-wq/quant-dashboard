#!/usr/bin/env python3
"""V6.15.6 append-only contradiction and invalidation memory."""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"registry"/"rules.json"
CLAIMS=ROOT/"research"/"state"/"source_claims.json"
SCORE=ROOT/"research"/"reports"/"rule_scorecards.json"
OUT=ROOT/"research"/"history"/"contradictions.json"
VERSION="6.15.6"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def rid(kind,payload):
    raw=json.dumps([kind,payload],ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "conf_"+hashlib.sha256(raw.encode()).hexdigest()[:20]

def action_side(rule):
    actions={str(x).lower() for x in ((rule or {}).get("normalized_rule") or {}).get("actions",[])}
    if actions & {"buy","add","planned_buy"} and not actions & {"sell","clear","trim","trim_half"}:return "bullish"
    if actions & {"sell","clear","trim","trim_half"} and not actions & {"buy","add","planned_buy"}:return "bearish"
    return None

def detect(registry,claims,scorecards):
    found=[]
    rules=[r for r in registry.get("rules") or [] if r.get("active",True)]
    by_author_symbol=defaultdict(list)
    for r in rules:
        for sym in r.get("symbols") or []:
            by_author_symbol[(r.get("author"),sym)].append(r)
    for (author,sym),rows in by_author_symbol.items():
        sides={action_side(r) for r in rows if action_side(r)}
        if len(sides)>1:
            payload={"author":author,"symbol":sym,"rule_ids":sorted(r.get("rule_id") for r in rows),"sides":sorted(sides)}
            found.append({"contradiction_id":rid("same_author_conflict",payload),"type":"same_author_conflict","status":"unresolved","payload":payload})

    # Explicit invalidation claims are linked conservatively by source_id only.
    invalid_by_source=defaultdict(list)
    for c in claims.get("claims") or []:
        if c.get("original_kind")=="invalidation":
            invalid_by_source[c.get("source_id")].append(c)
    for r in rules:
        inv=invalid_by_source.get(r.get("source_id")) or []
        if inv:
            payload={"rule_id":r.get("rule_id"),"source_id":r.get("source_id"),"invalidation_ids":sorted(c.get("proposition_id") for c in inv)}
            found.append({"contradiction_id":rid("rule_invalidation_present",payload),"type":"rule_invalidation_present","status":"context_only","payload":payload})

    # Official conflicts are recorded only when structured claim metadata explicitly
    # provides a shared contradiction_key and opposite stance. No semantic guessing.
    keyed=defaultdict(list)
    for c in claims.get("claims") or []:
        key=c.get("contradiction_key");stance=c.get("stance")
        if key and stance:keyed[key].append(c)
    for key,rows in keyed.items():
        official=[x for x in rows if x.get("verification_status")=="source_verified"]
        author=[x for x in rows if x.get("verification_status")=="unverified"]
        for o in official:
            for a in author:
                if o.get("stance")!=a.get("stance"):
                    payload={"key":key,"official":o.get("proposition_id"),"author":a.get("proposition_id")}
                    found.append({"contradiction_id":rid("author_official_conflict",payload),"type":"author_official_conflict","status":"unresolved","payload":payload})

    # Method conclusion conflicts require explicit conclusion labels; absence means no inference.
    by_method=defaultdict(set)
    for c in scorecards.get("cards") or []:
        conclusion=c.get("evaluated_conclusion")
        for m in c.get("primary_methods") or []:
            if conclusion:by_method[m].add(conclusion)
    for method,states in by_method.items():
        if "supportive" in states and "challenging" in states:
            payload={"method":method,"conclusions":sorted(states)}
            found.append({"contradiction_id":rid("method_conclusion_conflict",payload),"type":"method_conclusion_conflict","status":"unresolved","payload":payload})
    return found

def merge(found,prior=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    old={x.get("contradiction_id"):x for x in ((prior or {}).get("records") or [])}
    for x in found:
        cid=x["contradiction_id"]
        if cid not in old:
            x=dict(x);x["first_seen_at"]=now;x["last_seen_at"]=now;old[cid]=x
        else:
            old[cid]["last_seen_at"]=now
    return {"version":VERSION,"generated_at":now,"records":sorted(old.values(),key=lambda x:x.get("contradiction_id") or ""),"counts":{
        "total":len(old),"unresolved":sum(1 for x in old.values() if x.get("status")=="unresolved")
    }}

def main():
    prior=load(OUT,{})
    found=detect(load(REGISTRY,{}),load(CLAIMS,{}),load(SCORE,{}))
    out=merge(found,prior)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))
if __name__=="__main__":main()
