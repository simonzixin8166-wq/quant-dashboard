#!/usr/bin/env python3
"""D2 negative tests (GPT #133 6621145320): each evasion pattern planted into a real production entry makes the
isolation gate fail; the gate passes again after the file is restored. Files are restored byte for byte in finally."""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_retrieval_isolation as gate  # noqa: E402

TARGET = ROOT / "scripts" / "daily_skip_gate.py"          # a real Daily entry
REVIEWED = ROOT / "tests" / "test_v570_evidence_attribution.py"


def run() -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gate.main([])
    return rc, buf.getvalue()


@contextlib.contextmanager
def planted(path: Path, extra: str = None, replace: tuple = None, create: bool = False):
    existed = path.exists()
    orig = path.read_bytes() if existed else None
    try:
        if create:
            path.write_text(extra, encoding="utf-8")
        elif replace:
            path.write_text(orig.decode("utf-8").replace(*replace, 1), encoding="utf-8")
        else:
            path.write_bytes(orig + extra.encode("utf-8"))
        yield
    finally:
        if existed:
            path.write_bytes(orig)
        else:
            path.unlink(missing_ok=True)


assert run()[0] == 0, "gate must pass on the clean tree"
cases = [
    ("raw path", TARGET, "\n# research/index/x.jsonl\n", None, False, "research/index"),
    ("string concatenation", TARGET, '\n_P = "research" + "/index"\n', None, False, "squashed:research/index"),
    ("os.path.join pieces", TARGET, '\nimport os\n_P = os.path.join("research", "index")\n', None, False, "squashed:researchindex"),
    ("pathlib pieces", TARGET, '\n_P = Path("research") / "index"\n', None, False, "squashed:research/index"),
    ("blind set via concat", TARGET, '\n_B = "blind" + "_set"\n', None, False, "squashed:blind_set"),
    ("unreviewed dynamic import", TARGET, "\nimport importlib\n_m = importlib.import_module(_name)\n", None, False, "dynamic_import_unreviewed"),
    ("reviewed line edited", REVIEWED, None, ('spec=importlib.util.spec_from_file_location("ea",engine_path)',
                                              'spec=importlib.util.spec_from_file_location("ea",engine_path )'), False, "dynamic_import_unreviewed"),
]
# kr-0.3.2 (GPT 6624784358 D2): call sites and argument sources are pinned too, not only the helper line
COV = ROOT / "tests" / "test_coverage_truth.py"
V610 = ROOT / "tests" / "test_v610a_playbook_engine.py"
GATE_WF = ROOT / ".github" / "workflows" / "privacy-canary-gate.yml"
cases += [
    ("call-site argument replaced", COV, None, ('cov = load("cov_truth", "data_learning_coverage_audit.py")',
                                                'cov = load("cov_truth", "retrieval_eligibility.py")'), False, "call_sites line changed"),
    ("argument from environment", REVIEWED, None, ("engine_path=ROOT/'scripts/evidence_attribution_engine.py'",
                                                   "engine_path=ROOT/__import__('os').environ['X']"), False, "arg_sources line changed"),
    ("new call with concatenated path", COV, '\n_x = load("x", "retrieval" + "_x.py")\n', None, False, "unpinned call of reviewed helper"),
    ("unused helper gets called", V610, '\n_m = load_module("m", ROOT / "scripts" / "x.py")\n', None, False, "helper marked unused is called"),
    ("path variable reassigned", REVIEWED, "\nengine_path = ROOT / 'scripts' / 'other.py'\n", None, False, "assigned outside the pinned line"),
    ("excluded security/QA workflow edited", GATE_WF, "\n# edited\n", None, False, "security_qa_only_workflow changed"),
    ("yaml workflow outside the gate", ROOT / ".github" / "workflows" / "zz-probe.yaml", "name: x\non: push\n", None, True, "*.yaml workflow"),
]
for name, path, extra, rep, create, expect in cases:
    with planted(path, extra=extra, replace=rep, create=create):
        rc, out = run()
    assert rc == 1 and expect in out, (name, rc, out[-400:])
    print(f"PASS negative: {name} -> blocked ({expect})")

# kr-0.3.2 round 3 (GPT 6625522839 D2): the import graph follows relative imports, nested packages, package
# __init__.py and `scripts.` prefixed imports; a local-looking import that resolves to nothing fails closed.
import shutil  # noqa: E402
SCR = ROOT / "scripts"
FORBID = "SRC = 'research/index/build_audit.jsonl'\n"
graph_cases = [
    ("relative import inside a package", {"zz_rel_pkg/__init__.py": "from .inner import SRC\n", "zz_rel_pkg/inner.py": FORBID},
     "\nimport zz_rel_pkg\n", "zz_rel_pkg/inner.py"),
    ("nested package submodule", {"zz_pkg/__init__.py": "", "zz_pkg/sub/__init__.py": "", "zz_pkg/sub/deep.py": FORBID},
     "\nfrom zz_pkg.sub import deep\n", "zz_pkg/sub/deep.py"),
    ("package __init__ side effect", {"zz_pkg2/__init__.py": FORBID}, "\nfrom zz_pkg2 import SRC\n", "zz_pkg2/__init__.py"),
    ("scripts.-prefixed import", {"zz_mod.py": FORBID}, "\nfrom scripts.zz_mod import SRC\n", "zz_mod.py"),
    ("unresolvable local import", {}, "\nimport zz_missing_module_xyz\n", "unresolved_import"),
]
for name, files, extra, expect in graph_cases:
    made = []
    try:
        for rel, body in files.items():
            f = SCR / rel
            for d in reversed(f.relative_to(SCR).parents[:-1]):
                if not (SCR / d).exists():
                    (SCR / d).mkdir(); made.append(SCR / d)
            f.write_text(body, encoding="utf-8"); made.append(f)
        with planted(TARGET, extra=extra):
            rc, out = run()
    finally:
        for m in sorted(made, key=lambda x: -len(x.parts)):
            shutil.rmtree(m) if m.is_dir() else m.unlink(missing_ok=True)
    assert rc == 1 and expect in out, (name, rc, out[-600:])
    assert not any((SCR / r.split("/")[0]).exists() for r in files), "probe files left behind"
    print(f"PASS negative: {name} -> blocked ({expect})")

# indirect shell invocation: a workflow line `bash scripts/x.sh` pulls x.sh into the entry list
wf = ROOT / ".github" / "workflows" / "zz-probe-tmp.yml"
sh = ROOT / "scripts" / "zz_probe_tmp.sh"
with planted(sh, extra="#!/bin/sh\ncat research/index/build_audit.jsonl\n", create=True), \
        planted(wf, extra="name: probe\non: workflow_dispatch\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - run: bash scripts/zz_probe_tmp.sh\n", create=True):
    rc, out = run()
assert rc == 1 and "zz_probe_tmp.sh" in out, out[-400:]
print("PASS negative: workflow -> bash script -> forbidden path -> blocked")
with planted(wf, extra="name: probe\non: workflow_dispatch\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make index\n", create=True):
    rc, out = run()
assert rc == 1 and "unresolvable make target" in out, out[-400:]
print("PASS negative: workflow -> unresolvable make target -> blocked (fail closed)")
assert run()[0] == 0, "gate must pass again after restore"
assert not wf.exists() and not sh.exists()
print("PASS isolation negatives: all evasion patterns blocked; clean tree passes after restore")
