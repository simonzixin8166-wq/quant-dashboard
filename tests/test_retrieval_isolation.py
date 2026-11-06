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
# kr-0.3.2 (GPT 6624784358 D2): security / QA-only workflows may read research/index only to scan it. Each one is pinned
# by sha256 in isolation_exclusions.json and must stay read-only: no write permissions, no secrets other than the
# read-only GITHUB_TOKEN, no artifact upload, no push / deploy / Pages. Any edit changes the hash and fails the gate
# until it is reviewed again and the pin is updated.
EXCLUSIONS = ROOT / "research" / "specs" / "retrieval" / "isolation_exclusions.json"
SECURITY_QA_ONLY_WORKFLOWS = set(json.loads(EXCLUSIONS.read_text(encoding="utf-8"))["security_qa_only_workflow"]) if EXCLUSIONS.exists() else set()
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


# kr-0.3.2 round 3 (GPT 6625522839 D2): import graph. Absolute names are resolved against every import root the
# entry scripts use (repo root, scripts/, tests/), as module files, packages (__init__.py) and submodules
# (`from pkg import sub`); relative imports resolve against the importing file's package. A name that resolves to
# nothing local and is neither stdlib nor a reviewed third-party package is recorded as unresolved and fails the gate.
IMPORT_ROOTS = (ROOT, ROOT / "scripts", ROOT / "tests")
THIRD_PARTY = {"pandas", "numpy", "yfinance", "arch", "pandas_market_calendars"}  # the only packages workflows pip-install
STDLIB = set(sys.stdlib_module_names) | {"__future__"}
UNRESOLVED: list = []
IMPORT_RX = re.compile(r"^[ \t]*(?:from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+\(?([\w., \t*]+)|import[ \t]+([\w., \t]+))", re.M)


def _module_files(base: Path, dotted: str) -> list:
    parts = [x for x in dotted.split(".") if x]
    if not parts:
        return [base / "__init__.py"] if (base / "__init__.py").exists() else []
    out = []
    for i in range(len(parts), 0, -1):  # a.b.c -> a/b/c.py | a/b/c/__init__.py, then the parents' __init__ / module
        stem = base.joinpath(*parts[:i])
        for c in (stem.with_suffix(".py"), stem / "__init__.py"):
            if c.exists():
                out.append(c)
        if out:
            break
    return out


def resolve_import(path: Path, level: int, module: str, names: list) -> tuple:
    """(local files, unresolved flag). names = the imported names of `from module import names` (submodules)."""
    if level:
        base = path.parent
        for _ in range(level - 1):
            base = base.parent
        roots = [base]
    else:
        top = module.split(".")[0]
        if top in STDLIB or top in THIRD_PARTY:
            return [], False
        roots = list(IMPORT_ROOTS)
    files = []
    for r in roots:
        files += _module_files(r, module)
        for n in names:  # from pkg import submodule
            if n != "*":
                sub = r.joinpath(*[x for x in module.split(".") if x], n)
                files += [c for c in (sub.with_suffix(".py"), sub / "__init__.py") if c.exists()]
    return sorted(set(files)), not files


def local_imports(path: Path, seen: set) -> None:
    if path in seen or not path.exists() or path.suffix != ".py":
        return
    seen.add(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    for m in IMPORT_RX.finditer(text):
        if m.group(4):
            pairs = [(0, n.strip().split(" as ")[0].strip(), []) for n in m.group(4).split(",") if n.strip()]
        else:
            names = [n.strip().split(" as ")[0].strip() for n in m.group(3).split(",") if n.strip()]
            pairs = [(len(m.group(1)), m.group(2), names)]
        for level, module, names in pairs:
            files, unresolved = resolve_import(path, level, module, names)
            if unresolved:
                UNRESOLVED.append((str(path.relative_to(ROOT)), ("." * level) + module))
            for f in files:
                local_imports(f, seen)
            for f in files:  # importing pkg.sub also runs pkg/__init__.py
                for parent in f.parents:
                    if parent in (ROOT, ROOT.parent) or not str(parent).startswith(str(ROOT)):
                        break
                    if (parent / "__init__.py").exists():
                        local_imports(parent / "__init__.py", seen)
    # kr-0.3.2 D2: any string literal naming an existing scripts/*.py is followed too (covers importlib /
    # spec_from_file_location / runpy targets built from literals). Over-approximation: more files scanned, never fewer.
    for lit in re.findall(r"[\"']([\w./-]+?)(?:\.py)?[\"']", text):
        stem = Path(lit).name
        cand = ROOT / "scripts" / (stem + ".py")
        if stem and cand.exists():
            local_imports(cand, seen)


def entries() -> dict:
    wfs = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    prod_wf = [w for w in wfs if w.name not in RESEARCH_ONLY_WORKFLOWS | SECURITY_QA_ONLY_WORKFLOWS]
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


def _line_sha(lines, n):
    return hashlib.sha256(lines[n - 1].strip().encode("utf-8")).hexdigest() if 0 < n <= len(lines) else None


def review_problems(rev: dict) -> list:
    """Pinned helper, call sites and argument sources must be unchanged; targets must be literal and exist."""
    out = []
    for r in rev["reviewed"]:
        f = ROOT / r["file"]
        if not f.exists():
            out.append((r["file"], "reviewed file missing"))
            continue
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for kind in ("helper",):
            if _line_sha(lines, r[kind]["line"]) != r[kind]["line_sha256"]:
                out.append((f"{r['file']}:{r[kind]['line']}", f"{kind} line changed"))
        for kind in ("call_sites", "arg_sources"):
            for x in r[kind]:
                if _line_sha(lines, x["line"]) != x["line_sha256"]:
                    out.append((f"{r['file']}:{x['line']}", f"{kind} line changed"))
        name = r.get("helper_name")
        if name:  # every call of the helper must be a pinned call site; an unused helper must stay uncalled
            calls = [i for i, l in enumerate(lines, 1) if re.search(rf"(?<![\w.]){re.escape(name)}\(", l) and not re.match(rf"\s*def\s+{re.escape(name)}\(", l)]
            pinned = {x["line"] for x in r["call_sites"]}
            if not r["used"] and calls:
                out.append((f"{r['file']}:{calls[0]}", "helper marked unused is called"))
            for c in calls:
                if r["used"] and c not in pinned:
                    out.append((f"{r['file']}:{c}", "unpinned call of reviewed helper"))
        if r.get("path_variable"):  # a path variable must be assigned exactly once, on a pinned arg-source line
            assigns = [i for i, l in enumerate(lines, 1) if re.match(rf"\s*{re.escape(r['path_variable'])}\s*=", l)]
            if assigns != [x["line"] for x in r["arg_sources"]]:
                out.append((r["file"], f"{r['path_variable']} assigned outside the pinned line"))
        src = " ".join(lines[x["line"] - 1] for x in r["arg_sources"] if 0 < x["line"] <= len(lines))
        for t in r["targets"]:
            stem = Path(t).name
            if not (ROOT / t).exists() or not (stem in src or Path(t).stem in src):
                out.append((r["file"], f"target {t} not a literal in the pinned argument lines or missing"))
        if r["used"] and (not r["call_sites"] or not r["targets"]):
            out.append((r["file"], "used helper without pinned call sites / targets"))
    return out


def exclusion_problems() -> list:
    """Pinned sha256 of every excluded security/QA workflow and checker; workflows must stay read-only."""
    out = []
    if not EXCLUSIONS.exists():
        return [("isolation_exclusions.json", "missing")]
    ex = json.loads(EXCLUSIONS.read_text(encoding="utf-8"))
    for name, pin in ex["security_qa_only_workflow"].items():
        p = ROOT / ".github" / "workflows" / name
        if not p.exists() or sha(p) != pin:
            out.append((name, "security_qa_only_workflow changed: review again and update the pin"))
            continue
        t = p.read_text(encoding="utf-8")
        perms = re.findall(r"^\s+([\w-]+):\s*(read|write|none)\s*$", t, re.M)
        if any(v == "write" for _, v in perms) or "permissions:" not in t or re.search(r"permissions:\s*write-all", t):
            out.append((name, "write permission"))
        if re.search(r"secrets\.(?!GITHUB_TOKEN\b)", t):
            out.append((name, "uses a secret other than the read-only GITHUB_TOKEN"))
        if re.search(r"upload-artifact|deploy-pages|upload-pages-artifact|git\s+push|git\s+commit|gh-pages", t):
            out.append((name, "uploads, pushes or deploys"))
    for path, pin in ex["checker_pins"].items():
        if not (ROOT / path).exists() or sha(ROOT / path) != pin:
            out.append((path, "excluded checker changed: review again and update the pin"))
    return out


def main(argv) -> int:
    UNRESOLVED.clear()
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
    # kr-0.3.2 round 3: local-looking imports that resolve to nothing fail closed
    for f, mod in sorted(set(UNRESOLVED)):
        hits.append(("unresolved_import", f, mod))
    # make targets named in workflows must resolve to a reviewed Makefile; none exists, so any target fails closed
    for w in groups["workflows"]:
        for t in re.findall(r"\bmake\s+([\w-]+)", w.read_text(encoding="utf-8")):
            hits.append(("workflows", f"{w.relative_to(ROOT)}::make {t}", "unresolvable make target"))
    # dynamic imports / exec / eval with non-literal targets: must be in the reviewed list (file, line, line hash)
    rev = json.loads(REVIEW.read_text(encoding="utf-8"))
    review = {(r["file"], r["helper"]["line"], r["helper"]["line_sha256"]) for r in rev["reviewed"]}
    dyn = [d for files in groups.values() for p in files for d in dynamic_lines(p)]
    unreviewed = [d for d in dyn if (d["file"], d["line"], d["line_sha256"]) not in review]
    for d in unreviewed:
        hits.append(("dynamic_import_unreviewed", f"{d['file']}:{d['line']}", d["line_sha256"][:12]))
    for prob in review_problems(rev):
        hits.append(("dynamic_import_review_mismatch", prob[0], prob[1]))
    for prob in exclusion_problems():
        hits.append(("exclusion_changed_or_unsafe", prob[0], prob[1]))
    if list((ROOT / ".github" / "workflows").glob("*.yaml")) or (ROOT / ".github" / "actions").exists():
        hits.append(("workflows", ".github", "*.yaml workflow or local composite action: not covered by this gate"))
    # structural: Pages publishes docs/ only; the research index must never exist under docs/
    for bad in ("docs/research/index", "docs/research/blind_set_hashes.json", "docs/index_retrieval"):
        if (ROOT / bad).exists():
            hits.append(("pages_publish_dir", bad, "research index under docs/"))
    listing = {"gate": "retrieval-isolation", "forbidden_patterns": FORBIDDEN,
               "research_only_workflows_excluded": sorted(RESEARCH_ONLY_WORKFLOWS),
               "security_qa_only_workflows_excluded": sorted(SECURITY_QA_ONLY_WORKFLOWS), "checkers_excluded": sorted(CHECKERS),
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
          f"(raw and squashed), {len(dyn)} dynamic-import helper sites all reviewed "
          f"({sum(len(r['call_sites']) for r in rev['reviewed'])} pinned call-site lines), 0 unresolved local imports, docs/ holds no index")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
