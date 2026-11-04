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
for name, path, extra, rep, create, expect in cases:
    with planted(path, extra=extra, replace=rep, create=create):
        rc, out = run()
    assert rc == 1 and expect in out, (name, rc, out[-400:])
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
