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
# privacy-canary-gate.yml (kr-0.3.2 D4) only reads research/index to scan it for private data; read-only, no publish
RESEARCH_ONLY_WORKFLOWS = {"retrieval-inventory-check.yml", "privacy-canary-gate.yml"}
# the retrieval checkers themselves name the forbidden paths; they read no index and decide nothing
CHECKERS = {"tests/test_retrieval_isolation.py", "tests/test_retrieval_contracts.py", "tests/test_question_set_isolation.py",
            "tests/test_retrieval_eligibility_audit.py", "tests/test_privacy_canary_scan.py", "scripts/privacy_canary_scan.py",
            "tests/test_retrieval_isolation_negative.py"}
OUT = ROOT / "research" / "specs" / "retrieval" / "production_entry_list.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def workflow_scripts(text: str) -> set:
    found = set()
    for m in re.finditer(r"(?:python3?|node)\s+(?:-m\s+\S+\s+)?((?:scripts|tests|docs)/[\w./-]+\.(?:py|mjs|js))", text):
        found.add(m.group(1))
    # kr-0.3.2 D2: indirect invocations from workflow shell lines
    for m in re.finditer(r"(?:\bbash|\bsh|\bsource|\.)\s+\.?/?((?:scripts|tests|\.github)/[\w./-]+\.sh)\b", text):
        found.add(m.group(1))
    for m in re.finditer(r"\./((?:scripts|tests)/[\w./-]+\.(?:sh|py))\b", text):
        found.add(m.group(1))
    for m in re.finditer(r"python3?\s+-m\s+([\w.]+)", text):
        mod = m.group(1)
        for cand in (f"scripts/{mod.split('.')[-1]}.py", mod.replace(".", "/") + ".py"):
            if (ROOT / cand).exists():
                found.add(cand)
    for m in re.finditer(r"python3?\s+-c\s+([\"'])(.*?)\1", text, re.S):
        for name in re.findall(r"(?:from|import)\s+([\w.]+)", m.group(2)):
            cand = f"scripts/{name.split('.')[0]}.py"
            if (ROOT / cand).exists():
                found.add(cand)
    for m in re.finditer(r"\bmake\s+([\w-]+)", text):
        found.add(f"Makefile::{m.group(1)}")  # no Makefile exists today; a target name here fails closed below
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
    # kr-0.3.2 D2: any string literal naming an existing scripts/*.py is followed too (covers importlib /
    # spec_from_file_location / runpy targets built from literals). Over-approximation: more files scanned, never fewer.
    text = path.read_text(encoding="utf-8", errors="replace")
    for lit in re.findall(r"[\"']([\w./-]+?)(?:\.py)?[\"']", text):
        stem = Path(lit).name
        cand = ROOT / "scripts" / (stem + ".py")
        if stem and cand.exists():
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


DYN = re.compile(r"importlib\.import_module\(|__import__\(|runpy\.run_\w+\(|(?<![\w.])exec\(|(?<![\w.])eval\(|"
                 r"spec_from_file_location\(|\bimport\(\s*[^'\"\s]")
REVIEW = ROOT / "research" / "specs" / "retrieval" / "dynamic_import_review.json"


def squash(txt: str) -> str:
    """Join string pieces so concatenated or path-joined forbidden paths become visible:
    "research" + "/index", os.path.join("research", "index"), Path("research") / "index", `research/${x}`."""
    t = re.sub(r"os\.path\.join|Path|PurePath|path\.join", "", txt)
    t = re.sub(r"[\s'\"`+,()\\]", "", t)
    return t.replace("//", "/")


SQUASHED = ["research/index", "researchindex", "blind_set", "blindset", "knowledge_index", "knowledge_query", "retrieval_index"]


def dynamic_lines(p: Path) -> list:
    """Dynamic import / exec / eval call sites whose target is not a plain string literal on the same line."""
    out = []
    if p.suffix not in {".py", ".js", ".mjs", ".ts"}:
        return out
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if DYN.search(line):
            literal = re.search(r"(?:import_module|__import__|run_path|run_module)\(\s*[\"'][\w./-]+[\"']\s*\)", line)
            stdlib = re.search(r"__import__\(\s*[\"'](json|os|sys|re|math|time|datetime)[\"']\s*\)", line)
            # a path built only from literals that name an existing script is resolved (and followed by local_imports)
            named = [x for x in re.findall(r"[\"']([\w./-]+?\.py)[\"']", line) if (ROOT / "scripts" / Path(x).name).exists()]
            if literal or stdlib or named:
                continue
            out.append({"file": str(p.relative_to(ROOT)), "line": i,
                        "line_sha256": hashlib.sha256(line.strip().encode("utf-8")).hexdigest()})
    return out


def main(argv) -> int:
    groups = entries()
    hits = []
    for g, files in groups.items():
        for p in files:
            txt = p.read_text(encoding="utf-8", errors="replace")
            for pat in FORBIDDEN:
                if re.search(pat, txt):
                    hits.append((g, str(p.relative_to(ROOT)), pat))
            sq = squash(txt)
            for pat in SQUASHED:
                if pat in sq and not any(h[1] == str(p.relative_to(ROOT)) for h in hits):
                    hits.append((g, str(p.relative_to(ROOT)), f"squashed:{pat}"))
    # make targets named in workflows must resolve to a reviewed Makefile; none exists, so any target fails closed
    for w in groups["workflows"]:
        for t in re.findall(r"\bmake\s+([\w-]+)", w.read_text(encoding="utf-8")):
            hits.append(("workflows", f"{w.relative_to(ROOT)}::make {t}", "unresolvable make target"))
    # dynamic imports / exec / eval with non-literal targets: must be in the reviewed list (file, line, line hash)
    review = {(r["file"], r["line"], r["line_sha256"]) for r in json.loads(REVIEW.read_text(encoding="utf-8"))["reviewed"]}
    dyn = [d for files in groups.values() for p in files for d in dynamic_lines(p)]
    unreviewed = [d for d in dyn if (d["file"], d["line"], d["line_sha256"]) not in review]
    for d in unreviewed:
        hits.append(("dynamic_import_unreviewed", f"{d['file']}:{d['line']}", d["line_sha256"][:12]))
    # structural: Pages publishes docs/ only; the research index must never exist under docs/
    for bad in ("docs/research/index", "docs/research/blind_set_hashes.json", "docs/index_retrieval"):
        if (ROOT / bad).exists():
            hits.append(("pages_publish_dir", bad, "research index under docs/"))
    listing = {"gate": "retrieval-isolation", "forbidden_patterns": FORBIDDEN,
               "research_only_workflows_excluded": sorted(RESEARCH_ONLY_WORKFLOWS), "checkers_excluded": sorted(CHECKERS),
               "counts": {g: len(v) for g, v in groups.items()},
               "entries": {g: {str(p.relative_to(ROOT)): sha(p) for p in v} for g, v in groups.items()},
               "dynamic_import_sites": len(dyn), "dynamic_import_reviewed": len(dyn) - len(unreviewed),
               "hits": [{"group": g, "file": f, "pattern": pat} for g, f, pat in hits]}
    if "--write" in argv:
        OUT.write_text(json.dumps(listing, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert sum(listing["counts"].values()) > 50, f"entry list suspiciously small: {listing['counts']}"
    assert listing["counts"]["workflows"] >= 15 and listing["counts"]["frontend_pages_assets"] >= 10
    if hits:
        for h in hits:
            print(f"::error title=Retrieval isolation::{h}")
        return 1
    print(f"PASS retrieval isolation: {listing['counts']} entry files, 0 references to {FORBIDDEN} "
          f"(raw and squashed), {len(dyn)} dynamic-import sites all reviewed, docs/ holds no index")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
