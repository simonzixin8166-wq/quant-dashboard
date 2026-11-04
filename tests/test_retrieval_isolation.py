#!/usr/bin/env python3
"""Retrieval isolation gate (contracts kr-0.3 §4.4, GPT #133 6620929885 §D2/D4).

Builds the full list of production entry points and fails if any of them can reach the research-only retrieval index,
its query tool or blind-test data. Entry points:
  - every GitHub Actions workflow except the research-only allowlist below (schedules, dispatch chains, Server Action
    Watch, Guardian, deploy-supabase, Pages build inputs);
  - every script those workflows run, plus the local modules those scripts import, transitively;
  - every front-end file published by Pages (docs/**/*.html, *.js, *.mjs) and the service worker;
  - every Supabase edge function and migration.
Writes the list (with sha256 per file) to research/specs/retrieval/production_entry_list.json when --write is given.
Any hit is an error and exits 1; it is never a warning.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [r"research/index", r"blind_set", r"knowledge_index", r"knowledge_query", r"retrieval_index"]
# research-only workflows that may touch retrieval evidence; they never publish or decide anything
RESEARCH_ONLY_WORKFLOWS = {"retrieval-inventory-check.yml"}
# the retrieval checkers themselves name the forbidden paths; they read no index and decide nothing
CHECKERS = {"tests/test_retrieval_isolation.py", "tests/test_retrieval_contracts.py"}
OUT = ROOT / "research" / "specs" / "retrieval" / "production_entry_list.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def workflow_scripts(text: str) -> set:
    found = set()
    for m in re.finditer(r"(?:python3?|node)\s+(?:-m\s+\S+\s+)?((?:scripts|tests|docs)/[\w./-]+\.(?:py|mjs|js))", text):
        found.add(m.group(1))
    return found


def local_imports(path: Path, seen: set) -> None:
    if path in seen or not path.exists() or path.suffix != ".py":
        return
    seen.add(path)
    for m in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))", path.read_text(encoding="utf-8", errors="replace"), re.M):
        names = [m.group(1)] if m.group(1) else [n.strip().split(" as ")[0] for n in m.group(2).split(",")]
        for n in names:
            cand = ROOT / "scripts" / (n.split(".")[0] + ".py")
            local_imports(cand, seen)


def entries() -> dict:
    wfs = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    prod_wf = [w for w in wfs if w.name not in RESEARCH_ONLY_WORKFLOWS]
    scripts = set()
    for w in prod_wf:
        scripts |= workflow_scripts(w.read_text(encoding="utf-8"))
    scripts -= CHECKERS
    py = set()
    for s in sorted(scripts):
        local_imports(ROOT / s, py)
    other = {ROOT / s for s in scripts if not s.endswith(".py") and (ROOT / s).exists()}
    front = sorted(p for p in (ROOT / "docs").rglob("*") if p.suffix in {".html", ".js", ".mjs"} and p.is_file())
    supa = sorted(p for p in (ROOT / "supabase").rglob("*") if p.is_file()) if (ROOT / "supabase").exists() else []
    groups = {"workflows": prod_wf, "workflow_scripts_and_imports": sorted(py | other),
              "frontend_pages_assets": front, "supabase_functions_and_migrations": supa}
    return {k: [p for p in v] for k, v in groups.items()}


def main(argv) -> int:
    groups = entries()
    hits = []
    for g, files in groups.items():
        for p in files:
            txt = p.read_text(encoding="utf-8", errors="replace")
            for pat in FORBIDDEN:
                if re.search(pat, txt):
                    hits.append((g, str(p.relative_to(ROOT)), pat))
    listing = {"gate": "retrieval-isolation", "forbidden_patterns": FORBIDDEN,
               "research_only_workflows_excluded": sorted(RESEARCH_ONLY_WORKFLOWS), "checkers_excluded": sorted(CHECKERS),
               "counts": {g: len(v) for g, v in groups.items()},
               "entries": {g: {str(p.relative_to(ROOT)): sha(p) for p in v} for g, v in groups.items()},
               "hits": [{"group": g, "file": f, "pattern": pat} for g, f, pat in hits]}
    if "--write" in argv:
        OUT.write_text(json.dumps(listing, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert sum(listing["counts"].values()) > 50, f"entry list suspiciously small: {listing['counts']}"
    assert listing["counts"]["workflows"] >= 15 and listing["counts"]["frontend_pages_assets"] >= 10
    if hits:
        for h in hits:
            print(f"::error title=Retrieval isolation::{h}")
        return 1
    print(f"PASS retrieval isolation: {listing['counts']} entry files, 0 references to {FORBIDDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
