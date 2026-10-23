"""ERR-01 step 1: mechanical regression checks for past incidents (lessons E-02/E-14, E-03, E-07, E-11).
Static checks over the repository only - no network, no PyYAML, no live data - so they run the same locally and in CI.
Each baseline list below is the state reviewed on 2026-10-23; growing it requires a conscious edit in a PR."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dev_check_lists as dcl

WF_DIR = ROOT / ".github" / "workflows"
V56 = (WF_DIR / "v56-pr-validation.yml").read_text(encoding="utf-8")
ALL_WF = "".join(p.read_text(encoding="utf-8") for p in sorted(WF_DIR.glob("*.yml")))

# --- E-02 / E-14: every data file the page fetches must already exist in docs/ ------------------------------
# (10/22: the TP-01 front-end went live before Daily first wrote research/turning_point_checklist.json; the
#  browser 404 made Autonomous QA fail. Ship a front-end read only after its producer has run, or add a placeholder.)
NOT_FETCHED = {"docs/data.json",          # label text in autonomous-qa.js
               "myalpha-research.json"}   # download file name in knowledge.js
PATH_RE = re.compile(r"['\"`](?:\./)?([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:json|jsonl|csv))(?:\?[^'\"`]*)?['\"`]")
sources = sorted((ROOT / "docs" / "assets").glob("*.js")) + [ROOT / "docs" / "index.html"]
missing = []
for src in sources:
    for rel in set(PATH_RE.findall(src.read_text(encoding="utf-8"))):
        if rel not in NOT_FETCHED and not (ROOT / "docs" / rel).is_file():
            missing.append(f"{src.relative_to(ROOT)} -> docs/{rel}")
assert not missing, "front-end reads data files that do not exist yet (QA counts the 404 as fatal): " + "; ".join(missing)

# --- E-03: tests run by the PR workflow import only what CI installs --------------------------------------
# (10/20: a test imported yaml; CI has no PyYAML. The local machine did, so only CI caught it.)
installed = set()
for spec in re.findall(r"pip install ([^\n]+)", V56):
    installed |= {re.split(r"[<>=\[]", s.strip("\"'"))[0].lower() for s in spec.split() if not s.startswith("-")}
installed |= {"numpy"}  # installed by pandas
local = {p.stem for p in (ROOT / "scripts").glob("*.py")} | {p.stem for p in (ROOT / "tests").glob("*.py")} | {"scripts"}
py_tests = re.findall(r"^\s+python (tests/\S+\.py)", V56, re.M)
assert py_tests, "no python tests parsed from v56-pr-validation.yml"
bad = []
for t in py_tests:
    for node in ast.walk(ast.parse((ROOT / t).read_text(encoding="utf-8"))):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods = [node.module.split(".")[0]]
        bad += [f"{t}: {m}" for m in mods if m not in sys.stdlib_module_names and m not in local and m.lower() not in installed]
assert not bad, "tests import packages CI does not install: " + "; ".join(sorted(set(bad)))
NODE_OK = {"assert", "fs", "path", "vm", "os", "child_process", "util"}
for t in re.findall(r"^\s+node (tests/\S+\.js)", V56, re.M):
    for req in re.findall(r"require\(['\"]([^'\"]+)['\"]\)", (ROOT / t).read_text(encoding="utf-8")):
        name = req.removeprefix("node:").split("/")[0]
        assert req.startswith((".", "/")) or name in NODE_OK, f"{t} requires {req}, which CI does not install"

# --- E-07: date bombs - tests that mix the real clock with fixed calendar dates ---------------------------
# (10/19: a test hard-coded a date that silently expired once the data moved past it.)
# Existing files are grandfathered as found on 2026-10-23 (not individually reviewed yet); a new test that
# reads the real clock AND hard-codes a date must derive the date from the data instead, or be added here.
DATE_BOMB_BASELINE = {
    "tests/author_signal_row.test.js", "tests/option_decision.test.js", "tests/option_scenarios.test.js",
    "tests/test_daily_guardian.py", "tests/test_system_status_center.py", "tests/test_v611_outcome_foundation.py",
    "tests/test_v611_walk_forward_replay.py", "tests/test_v614_source_reading_memory.py",
    "tests/test_v6145_source_rule_lifecycle.py",
}
CLOCK = re.compile(r"datetime\.now|date\.today|datetime\.utcnow|Date\.now\(|new Date\(\)")
LITERAL_DATE = re.compile(r"20\d\d-\d\d-\d\d")
run_files = re.findall(r"^\s+(?:python|node) (tests/\S+)", V56, re.M)
new_bombs = sorted(f for f in run_files if f not in DATE_BOMB_BASELINE and f != "tests/test_err01_regressions.py"
                   and CLOCK.search(t := (ROOT / f).read_text(encoding="utf-8")) and LITERAL_DATE.search(t))
assert not new_bombs, "test mixes the real clock with a fixed date (possible date bomb): " + ", ".join(new_bombs)

# --- E-11: command lists come from the workflows; every referenced test exists; new tests are registered ----
# (10/21: a v56 list copied from another branch pointed at missing tests.)
assert len(dcl.v56_commands()) == len(re.findall(r"^\s+(?:python|node) .+$", V56, re.M))
verify = dcl.daily_verify_commands()
assert len(verify) >= 50 and any("private_guardrail.py" in c for c in verify), len(verify)
refs = set(re.findall(r"(tests/[A-Za-z0-9_.-]+\.(?:py|js|mjs))", ALL_WF))
dangling = sorted(r for r in refs if not (ROOT / r).is_file())
assert not dangling, "workflows reference missing test files: " + ", ".join(dangling)
UNREGISTERED_BASELINE = {  # test files on disk that no workflow runs, as found on 2026-10-23 (to review, not to delete)
    "tests/brightline_method_map.test.js", "tests/stock_research_and_operations.test.js",
    "tests/test_research_brief_v41.py", "tests/test_thesis_revision_outcome_memory.py", "tests/test_trend_pulse_backtest.py",
    "tests/test_trend_pulse_v43.py", "tests/test_v496_layout_hotfix.py", "tests/test_v497_options_decision.py",
    "tests/test_wenxuecity.py", "tests/trading_calendar_parity.test.js",
}
on_disk = {f"tests/{p.name}" for p in (ROOT / "tests").iterdir()
           if p.suffix in (".py", ".js", ".mjs") and (p.name.startswith("test_") or ".test." in p.name)}
unregistered = sorted(on_disk - refs - UNREGISTERED_BASELINE)
assert not unregistered, "new test files are not run by any workflow (add them to v56-pr-validation.yml): " + ", ".join(unregistered)

print(f"PASS ERR-01 regressions: {len(sources)} front-end sources, {len(py_tests)} python tests' imports, "
      f"{len(run_files)} CI test files date-bomb scanned, {len(verify)} Daily verify commands parsed")
