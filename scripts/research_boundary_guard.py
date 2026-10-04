#!/usr/bin/env python3
"""Research/production dependency and write-boundary guard for V6.15."""
from __future__ import annotations
import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_WRITE_PREFIXES=("config/","data/ledger/","docs/data/","docs/assets/")
DEFAULT_RESEARCH_WRITE_PREFIXES=("research/",)
RESEARCH_READ_MARKERS=(
    "method_memory.json","learning_evaluation.json","controlled_learning_policy.json",
    "source_rule_lifecycle.json","self_improvement",
)
PRODUCTION_MODULES=("scripts/playbook_engine.py","scripts/fetch_and_build.py","scripts/private_ledger.py")
MANIFEST=ROOT/"research"/"specs"/"production_boundary_manifest.json"
EVIDENCE_LOCK=ROOT/"config"/"research_evidence_lock.json"
EVALUATION_SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
FAMILY_DEF=ROOT/"research"/"specs"/"rule_family_definition.json"

def canonical_hash(path):
    data=json.loads(path.read_text(encoding="utf-8"))
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def check_evidence_lock():
    lock=json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    problems=[]
    if canonical_hash(EVALUATION_SPEC)!=lock.get("evaluation_spec_canonical_sha256"):
        problems.append("evaluation_spec_hash_mismatch")
    if canonical_hash(FAMILY_DEF)!=lock.get("rule_family_definition_canonical_sha256"):
        problems.append("rule_family_definition_hash_mismatch")
    spec=json.loads(EVALUATION_SPEC.read_text(encoding="utf-8"))
    fam=json.loads(FAMILY_DEF.read_text(encoding="utf-8"))
    if spec.get("spec_version")!=lock.get("evaluation_spec_version"):
        problems.append("evaluation_spec_version_mismatch")
    if fam.get("definition_version")!=lock.get("rule_family_definition_version"):
        problems.append("rule_family_definition_version_mismatch")
    if fam.get("definition_hash")!=lock.get("rule_family_semantic_definition_hash"):
        problems.append("rule_family_semantic_hash_mismatch")
    return problems

def sha(path):
    p=ROOT/path
    if not p.exists():return None
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load_manifest():
    try:
        data=json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"cannot load production boundary manifest: {exc}")
    if not data.get("protected_prefixes") and not data.get("protected_files"):
        raise RuntimeError("production boundary manifest is empty")
    return data

def _tree_files(prefix):
    base=ROOT/prefix
    if base.is_file():
        return [base]
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file())

def snapshot():
    manifest=load_manifest()
    files={}
    for rel in manifest.get("protected_files") or []:
        files[rel]=sha(rel)
    for prefix in manifest.get("protected_prefixes") or []:
        for p in _tree_files(prefix):
            rel=p.relative_to(ROOT).as_posix()
            files[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "manifest_version":manifest.get("manifest_version"),
        "files":dict(sorted(files.items())),
    }

def check_manifest_completeness():
    manifest=load_manifest()
    protected=set(manifest.get("protected_files") or [])
    prefixes=tuple(manifest.get("protected_prefixes") or [])
    required=[
        "config/playbooks.public.json",
        "scripts/playbook_config.py",
        "scripts/fetch_and_build.py",
        "scripts/autonomous_research_planner.py",
        "docs/research/ledger_anchor.json",
    ]
    missing=[]
    for rel in required:
        if rel in protected or any(rel.startswith(p) for p in prefixes):
            continue
        missing.append(rel)
    return missing

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

def normalize_git_path(raw):
    p=str(raw or "").strip().replace("\\","/")
    if " -> " in p:
        p=p.split(" -> ",1)[1]
    return p

def check_changed_paths(paths):
    bad=[]
    for raw in paths:
        p=normalize_git_path(raw)
        if any(p.startswith(x) for x in FORBIDDEN_WRITE_PREFIXES):
            bad.append(p)
    return bad

def check_allowed_paths(paths,allowed_prefixes=DEFAULT_RESEARCH_WRITE_PREFIXES):
    bad=[]
    allowed=tuple(str(x).replace("\\","/") for x in allowed_prefixes)
    for raw in paths:
        p=normalize_git_path(raw)
        if p and not any(p.startswith(prefix) for prefix in allowed):
            bad.append(p)
    return bad

def git_worktree_paths():
    output=subprocess.check_output(
        ["git","status","--porcelain=v1","--untracked-files=all"],
        cwd=ROOT,text=True,stderr=subprocess.STDOUT,
    )
    paths=[]
    for line in output.splitlines():
        if not line.strip():continue
        paths.append(line[3:] if len(line)>=4 else line)
    return paths

def git_staged_paths():
    output=subprocess.check_output(
        ["git","diff","--cached","--name-only"],
        cwd=ROOT,text=True,stderr=subprocess.STDOUT,
    )
    return [x.strip() for x in output.splitlines() if x.strip()]

def assert_allowed(paths,allowed_prefixes=DEFAULT_RESEARCH_WRITE_PREFIXES,label="worktree"):
    bad=check_allowed_paths(paths,allowed_prefixes)
    if bad:
        print(json.dumps({
            "ok":False,
            "boundary":label,
            "allowed_prefixes":list(allowed_prefixes),
            "violations":bad,
        },ensure_ascii=False,indent=2))
        return 3
    print(json.dumps({
        "ok":True,
        "boundary":label,
        "allowed_prefixes":list(allowed_prefixes),
        "changed_paths":len(list(paths)),
    },ensure_ascii=False))
    return 0

def main():
    if "--snapshot" in sys.argv:
        print(json.dumps(snapshot(),ensure_ascii=False,sort_keys=True)); return 0
    if "--assert-worktree-research-only" in sys.argv:
        return assert_allowed(git_worktree_paths(),label="worktree_research_only")
    if "--assert-staged-research-only" in sys.argv:
        return assert_allowed(git_staged_paths(),label="staged_research_only")
    lock_problems=check_evidence_lock()
    if lock_problems:
        print(json.dumps({"ok":False,"evidence_lock_violations":lock_problems},ensure_ascii=False,indent=2))
        return 6
    missing=check_manifest_completeness()
    if missing:
        print(json.dumps({"ok":False,"manifest_missing_required_coverage":missing},ensure_ascii=False,indent=2))
        return 5
    violations=check_production_reads()
    if violations:
        print(json.dumps({"ok":False,"production_read_violations":violations},ensure_ascii=False,indent=2))
        return 2
    print(json.dumps({"ok":True,"production_read_violations":[]},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
