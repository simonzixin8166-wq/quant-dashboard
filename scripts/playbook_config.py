#!/usr/bin/env python3
"""Load the V6.10a public bootstrap Playbook registry.

The three Cloud Playbooks in this file mirror thresholds that were already
public in production code. Private account-dependent Playbooks must never be
added here.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONFIG_PATH=ROOT/"config"/"playbooks.public.json"

def load_registry(path:Path=CONFIG_PATH):
    return json.loads(path.read_text(encoding="utf-8"))

_REGISTRY=load_registry()
CORE_TIERS=_REGISTRY["core_tiers"]
PLAYBOOKS={row["playbook_id"]:row for row in _REGISTRY["playbooks"]}
TQQQ_RULES=PLAYBOOKS["CP-02"]["rules"]
LEAPS_RULES=PLAYBOOKS["CP-03"]["rules"]

def canonical_rule(playbook_id:str):
    row=PLAYBOOKS[playbook_id]
    frozen={k:v for k,v in row.items() if k not in {"evidence","lifecycle","notifications_enabled","ledger_enabled","enabled"}}
    return json.dumps(frozen,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def rule_hash(playbook_id:str):
    return hashlib.sha256(canonical_rule(playbook_id).encode("utf-8")).hexdigest()

def cloud_playbooks():
    return [row for row in _REGISTRY["playbooks"] if row.get("class")=="cloud"]

if __name__=="__main__":
    print(json.dumps({p["playbook_id"]:rule_hash(p["playbook_id"]) for p in cloud_playbooks()},ensure_ascii=False,indent=2))
