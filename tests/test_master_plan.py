"""#133 6117671408: the Master Execution Plan is complete, internally consistent and the Markdown is in sync."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import master_plan as mp  # noqa: E402

plan = mp.load()
assert mp.validate(plan) == [], mp.validate(plan)
assert mp.MD.read_text(encoding="utf-8") == mp.render(plan), "run: python scripts/master_plan.py render"
ids = {t["id"] for t in plan["tasks"]}
assert mp.REQUIRED <= ids
# the owner-named work streams are present by name
titles = " ".join(t["title"] for t in plan["tasks"])
for k in ("precedents", "fundamentals-outcome", "Shared evidence contract", "Unified SEC fetcher", "19 STOOQ", "display_watchlist", "flat bars"):
    assert k in titles, k
assert not any("oos_validated" in t["stages"] for t in plan["tasks"]), "learning stays UNPROVEN"
assert any("UNPROVEN" in g for g in plan["guardrails"])
print("test_master_plan OK")
