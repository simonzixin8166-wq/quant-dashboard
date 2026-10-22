"""#133 6148675138: Research Evidence Update must not overwrite research/ files merged after its compute SHA
(a9ae592 reverted #239/#240 by downloading a stale research/ artifact over a newer main checkout)."""
from pathlib import Path
wf = (Path(__file__).resolve().parents[1] / ".github/workflows/research-evidence-update.yml").read_text(encoding="utf-8")
commit = wf[wf.index("\n  commit:"):]
dl, guard, add = commit.index("Download research artifacts"), commit.index("lost-update guard"), commit.index("git add research/")
assert dl < guard < add, "guard must run after the artifact download and before git add"
assert 'git diff --name-only "${{ github.sha }}" HEAD -- research/' in commit and "git checkout HEAD --" in commit
print("test_reu_lost_update_guard OK")
