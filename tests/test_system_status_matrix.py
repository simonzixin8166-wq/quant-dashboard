"""HEALTH-01 (#133 6282755378): system status state matrix — attention only for critical failures, degraded (with
reasons) for non-critical ones, never a silent 'ok' while an isolated module has just failed."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import system_status_center as ssc  # noqa: E402

now = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
iso = lambda h: (now - timedelta(hours=h)).isoformat()
none = {"modules": {}}
C = lambda critical=("ok",), rc="ok", af=(), ledger=False, pb=False, failures=none: ssc.classify_overall(list(critical), rc, list(af), ledger, pb, failures, now)

# 1 all healthy
assert C()[0] == "ok" and C()[1] == []
# 2 Daily failed / unknown / running
assert C(critical=("bad",))[0] == "attention" and C(critical=(None,))[0] == "attention" and C(critical=("running",))[0] == "running"
# 3 market data stale (critical artifact excluded) / ledger fault / unresolved playbook
assert C(af=("market_dashboard",))[0] == "attention" and C(ledger=True)[0] == "attention" and C(pb=True)[0] == "attention"
# 4 the 10/20 incident: research-close failed while market data fresh → degraded, not attention, reason given
o, reasons, *_ = C(rc="bad")
assert o == "degraded" and any("research-close" in r and "不受影响" in r for r in reasons)
# 5 isolated module failed in the last run → degraded with its name; stale marker (>26h) no longer counts
f = {"modules": {"fred_macro": {"failed_at": iso(2)}, "auto_research": {"failed_at": iso(40)}}}
o, reasons, active, crit = C(failures=f)
assert o == "degraded" and set(active) == {"fred_macro"} and any(r.startswith("fred_macro") for r in reasons) and not crit
# 6 forward observations missed → attention (cannot be back-filled), even when everything else is fine
o, reasons, active, crit = C(failures={"modules": {"forward_observations": {"failed_at": iso(1)}}})
assert o == "attention" and crit == {"forward_observations"}
# 7 a critical failure is never downgraded to degraded by an extra non-critical reason
assert C(critical=("bad",), rc="bad")[0] == "attention"

# consumers accept degraded as trustworthy market data but still block attention
srv = (ROOT / "scripts" / "server_action_engine.py").read_text(encoding="utf-8")
assert 'ok=overall in {"ok","running","degraded"}' in srv
pi = (ROOT / "docs" / "assets" / "product-intelligence.js").read_text(encoding="utf-8")
assert "sys.overall==='attention'||sys.overall==='unknown'" in pi and "['ok','running','degraded']" in pi
# every continue-on-error Daily step now leaves a visible failure marker
import re  # noqa: E402  (CI has no PyYAML: parse the step list textually)
wf = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
steps = re.split(r"\n      - ", wf.split("\n    steps:\n", 1)[1])
coe = [st for st in steps if re.search(r"^\s*continue-on-error:\s*true\s*$", st, re.M)]
assert len(coe) >= 20, len(coe)
missing = []
for st in coe:
    m = re.search(r"^\s*id:\s*(\S+)\s*$", st, re.M)
    name = st.splitlines()[0]
    cond = f"if: steps.{m.group(1)}.outcome == 'failure'" if m else None
    if not cond or not any(cond in x and "module_failure_marker.py" in x for x in steps):
        missing.append(name)
assert not missing, missing
print("PASS system status matrix: ok/running/degraded/attention, markers on every isolated step")
