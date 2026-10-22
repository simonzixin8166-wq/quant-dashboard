"""P0 (#133 6205646800) regression: the Daily 'Commit and push' step must stage every tracked file the run writes.

Reproduces the 2026-10-15/16 failure: bootstrap_replay_history appends data/history/corrections.jsonl (VIX restatement
provenance); the step did not stage it, so `git pull --rebase` refused ("You have unstaged changes"). The real step is
executed (up to, not including, pull/push) in a throw-away git repo."""
import re, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wf = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
m = re.search(r"- name: Commit and push\n\s+run: \|\n((?:\s{10}.*\n)+)", wf)
assert m, "Commit and push step not found"
lines = [l[10:] for l in m.group(1).splitlines()]
cut = next(i for i, l in enumerate(lines) if l.startswith("git pull"))
script = "set -e\n" + "\n".join(lines[:cut]) + "\n"
assert "data/history/corrections.jsonl" in script and "git diff --name-only" in script


def repo(extra_dirty=None):
    t = Path(tempfile.mkdtemp())
    run = lambda *a: subprocess.run(a, cwd=t, check=True, capture_output=True, text=True)
    run("git", "init", "-q"); run("git", "config", "user.email", "t@t"); run("git", "config", "user.name", "t")
    for p in ("docs/data.json", "data/history/corrections.jsonl", "data/history/stooq_watchlist.zip", "research/audit/other.json",
              "research/archive/a.jsonl", "research/knowledge/k.jsonl", "research/store/source_store.json"):
        (t / p).parent.mkdir(parents=True, exist_ok=True)
        (t / p).write_text("{}\n")
    run("git", "add", "-A"); run("git", "commit", "-qm", "base")
    (t / "docs/data.json").write_text('{"x": 1}\n')
    with (t / "data/history/corrections.jsonl").open("a") as f:      # what bootstrap_replay_history does
        f.write('{"symbol": "VIX", "date": "2026-10-14", "applied": true}\n')
    if extra_dirty:
        (t / extra_dirty).write_text('{"changed": true}\n')
    return t


ok = repo()
r = subprocess.run(["bash", "-c", script], cwd=ok, capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
assert subprocess.run(["git", "diff", "--name-only"], cwd=ok, capture_output=True, text=True).stdout == ""
log = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=ok, capture_output=True, text=True).stdout
assert "data/history/corrections.jsonl" in log, "restatement provenance must be committed (append-only evidence)"

bad = repo(extra_dirty="research/audit/other.json")
r = subprocess.run(["bash", "-c", script], cwd=bad, capture_output=True, text=True)
assert r.returncode == 1 and "research/audit/other.json" in r.stdout and "::error title=Daily commit::" in r.stdout
assert (bad / "research/audit/other.json").read_text() == '{"changed": true}\n'   # nothing discarded or reset
print("PASS daily commit staging")
