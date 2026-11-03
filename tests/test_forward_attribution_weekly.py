"""Weekly forward attribution (fea-0.2 / rfi-0.1): report-only, deterministic, writes only on change."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_cohort_report as fcr  # noqa: E402
import forward_attribution_weekly as faw  # noqa: E402

# 1) attribution path on the frozen, fully matured promoted pilot (2026-09-29/30)
out, issues, s = fcr.run(ROOT, "promoted", "2026-09-29,2026-09-30", 20, stamp=False)
md = "\n".join(out)
assert s["rows"] == 36 and not issues, (s["rows"], issues)
assert "INCONSISTENT" not in md and "## 4. Attribution" in md
assert s["misses"] == sum(s["misses_by_primary"].values())
assert s["unattributed_R0"] == s["misses_by_primary"].get("R0", 0)
assert 0 <= s["attribution_coverage"] <= 1
assert s["production_effect"] == "none" and s["learning_state"] == "UNPROVEN" and s["final"] == "NO"
assert "run at" not in md  # stamp=False -> deterministic content
print("PASS cohort report run(): denominators consistent, attribution summary matches the table")

# 2) weekly cohort selection: only sessions whose rows are all final; nothing matured -> NOT RUN, never PASS
summary, md = faw.build(ROOT, datetime(2026, 11, 3, tzinfo=timezone.utc))
if not summary["rows"]:
    assert summary["engineering_acceptance"] == "NOT RUN" and summary["sessions"] == []
assert summary["engineering_acceptance"] in {"NOT RUN", "PASS", "CHECK"}

# 3) write only when content changed; generated_at alone never causes a rewrite
tmp = Path(tempfile.mkdtemp())
j, m = tmp / "a.json", tmp / "r" / "a.md"
assert faw.write_if_changed(summary, md, j, m) is True
again, md2 = faw.build(ROOT, datetime(2026, 11, 10, tzinfo=timezone.utc))
assert again["content_sha"] == summary["content_sha"]
assert faw.write_if_changed(again, md2, j, m) is False
assert json.loads(j.read_text(encoding="utf-8"))["generated_at"].startswith("2026-11-03")
print("PASS weekly attribution: cohort selection, NOT RUN when nothing matured, write-only-on-change")
