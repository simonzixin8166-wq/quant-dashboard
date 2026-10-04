#!/usr/bin/env python3
"""V6.15.8c generated research component manifest."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"specs"/"component_registry.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"component_manifest.json"
VERSION="6.15.8c"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def sha_file(rel):
    p=ROOT/rel
    if not p.exists():return None
    return hashlib.sha256(p.read_bytes()).hexdigest()

def build(registry,spec):
    rows=[]
    for c in registry.get("components") or []:
        row=dict(c)
        row["code_sha256"]=sha_file(c.get("script"))
        row["artifact_sha256"]=sha_file(c.get("artifact"))
        row["artifact_required"]=bool(c.get("artifact_required",True))
        rows.append(row)
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "app_version_policy":"independent_internal_component_versions",
        "evaluation_spec_version":spec.get("spec_version"),
        "family_definition_hash":(spec.get("definitions") or {}).get("rule_family_definition_hash"),
        "components":rows,
        "counts":{
            "components":len(rows),
            "missing_code_hashes":sum(1 for x in rows if not x.get("code_sha256")),
            "missing_artifact_hashes":sum(1 for x in rows if not x.get("artifact_sha256")),
            "missing_required_artifact_hashes":sum(1 for x in rows if x.get("artifact_required") and not x.get("artifact_sha256")),
        },
        "guardrails":registry.get("guardrails") or [],
    }

def main():
    out=build(load(REGISTRY,{}),load(SPEC,{}))
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
