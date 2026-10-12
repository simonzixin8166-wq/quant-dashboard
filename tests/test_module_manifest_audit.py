"""#133 P1-B: module manifest audit invariants on the real repository (read-only)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import module_manifest_audit as m  # noqa: E402

rep = m.build(with_git=False)
# every reader of a research artifact has a reviewed role — a new reader fails CI until its role is reviewed
assert rep["unclassified_readers"] == [], f"classify these readers in ROLES: {rep['unclassified_readers']}"
arts = {a["artifact"].split("/")[-1]: a for a in rep["artifacts"]}
assert all(a["producers"] for a in arts.values()), "every artifact needs a producer"
# monitor/display reads never count as research reach
for a in arts.values():
    for r in a["reaches_research_or_decision"]:
        assert m.ROLES.get(r, (None,))[0] in (m.R, m.D), (a["artifact"], r)
    assert set(a["direct_research_or_decision_consumers"]) <= set(a["reaches_research_or_decision"])
# owner-facing outputs are chain endpoints, not "monitor-only" problems
assert arts["server_action_status.json"]["kind"] == "owner_facing_output"
assert "monitor_or_display_only" not in arts["investment_actions_status.json"]["flags"]
# the matured-outcome memories are reported honestly when nothing in research reads them
s = rep["summary"]
assert set(s["outcome_without_research"]) == {a for a, x in arts.items() if "outcome_without_research" in x["flags"]}
# tracks are separate, never summed
t = rep["tracks"]
assert set(t) >= {"genuine_forward_fo10", "promoted_forward_separate_group", "auto_research_shadow"} and "never summed" in t["rule"]
assert t["auto_research_shadow"]["forward_eligible"] is False
assert "total" not in t and "combined" not in t
# experience citation status follows the data
e = rep["experience_citation"]
assert (e["status"] == "wired") == (e["records_citing_past_cases"] > 0)
assert rep["read_only"] is True and rep["production_use"] is False and rep["learning_state"] == "UNPROVEN"
md = m.markdown(rep)
assert "never summed" in md and "| artifact |" in md
print("test_module_manifest_audit OK")
