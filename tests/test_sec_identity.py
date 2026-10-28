"""SEC fair-access identity: the contact comes only from the SEC_USER_AGENT secret, never from the public repo or an
artifact; unset / empty / malformed values keep the previous identity (behaviour unchanged until the Owner adds it)."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sec_identity as si

for v in (None, "", "   ", "MyAlphaView no-contact", "x@y" * 100):
    if v is None:
        os.environ.pop("SEC_USER_AGENT", None)
    else:
        os.environ["SEC_USER_AGENT"] = v
    assert si.user_agent() == si.FALLBACK and si.configured() is False, v
os.environ["SEC_USER_AGENT"] = "  MyAlphaView research owner@example.com "
assert si.user_agent() == "MyAlphaView research owner@example.com" and si.configured() is True

# every SEC caller uses the helper; no hard-coded SEC identity or direct env read remains
callers = ["official_evidence_engine", "company_fundamental_memory", "turning_point_checklist", "sec_facts_v2",
           "sec_fundamentals", "fetch_and_build"]
for name in callers:
    src = (ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8")
    assert "from sec_identity import user_agent as sec_user_agent" in src and "except ModuleNotFoundError" in src, name
    assert 'os.getenv("SEC_USER_AGENT"' not in src and "os.getenv('SEC_USER_AGENT'" not in src, name

# the three production workflows that run SEC callers pass the secret (value never in the repo)
for wf in ("daily.yml", "daily-research.yml", "source-intelligence-validation.yml"):
    text = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
    assert "SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}" in text, wf

# no contact email of the SEC identity is committed anywhere in scripts/ or workflows
pat = re.compile(r"SEC_USER_AGENT[^\n]*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
for p in list((ROOT / "scripts").glob("*.py")) + list((ROOT / ".github" / "workflows").glob("*.yml")):
    assert not pat.search(p.read_text(encoding="utf-8")), p
print("PASS SEC identity: secret-only contact, fallback unchanged, all callers wired")
