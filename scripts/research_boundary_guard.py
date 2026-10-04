#!/usr/bin/env python3
"""Research/production dependency and write-boundary guard for V6.15."""
from __future__ import annotations
import hashlib, json, os, re, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_WRITE_PREFIXES=("config/","data/ledger/","docs/data/","docs/assets/")
RESEARCH_READ_MARKERS=(
    "method_memory.json","learning_evaluation.json","controlled_learning_policy.json",
    "source_rule_lifecycle.json","self_improvement",
)
PRODUCTION_MODULES=("scripts/playbook_engine.py","scripts/fetch_and_build.py","scripts/private_ledger.py")
HASH_TARGETS=(
    "config/playbooks.public.json",
    "scripts/playbook_config.py",
    "docs/research/ledger_anchor.json",
)
RULE_HASH_FILES=(
    "docs/data.json",
)

def sha(path):
    p=ROOT/path
    if not p.exists():return None
    return hashlib.sha256(p.read_bytes()).hexdigest()

def snapshot():
    out={"targets":{p:sha(p) for p in HASH_TARGETS},"rule_hashes":{}}
    for p in RULE_HASH_FILES:
        q=ROOT/p
        if q.exists():
            try:
                d=json.loads(q.read_text(encoding="utf-8"))
                if isinstance(d,dict):
                    vals={}
                    def walk(x,prefix=""):
                        if isinstance(x,dict):
                            for k,v in x.items():
                                key=f"{prefix}.{k}" if prefix else k
                                if "rule_hash" in str(k).lower():
                                    vals[key]=v
                                else: walk(v,key)
                        elif isinstance(x,list):
                            for i,v in enumerate(x): walk(v,f"{prefix}[{i}]")
                    walk(d)
                    out["rule_hashes"][p]=vals
            except Exception:
                out["rule_hashes"][p]={"parse_error":True}
    return out

def check_production_reads():
    violations=[]
    for rel in PRODUCTION_MODULES:
        p=ROOT/rel
        if not p.exists():continue
        text=p.read_text(encoding="utf-8",errors="ignore")
        for marker in RESEARCH_READ_MARKERS:
            if marker in text:
                violations.append({"file":rel,"marker":marker})
    return violations

def check_changed_paths(paths):
    bad=[]
    for raw in paths:
        p=str(raw).replace("\\","/")
        if any(p.startswith(x) for x in FORBIDDEN_WRITE_PREFIXES):
            bad.append(p)
    return bad

def main():
    if "--snapshot" in sys.argv:
        print(json.dumps(snapshot(),ensure_ascii=False,sort_keys=True)); return 0
    violations=check_production_reads()
    if violations:
        print(json.dumps({"ok":False,"production_read_violations":violations},ensure_ascii=False,indent=2))
        return 2
    print(json.dumps({"ok":True,"production_read_violations":[]},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
