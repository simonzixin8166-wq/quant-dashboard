"""Assignment preference: migration contract + modal wiring in generator and published page stay in sync."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
mig = (ROOT / "supabase/migrations/202610100001_option_assignment_preference.sql").read_text()
assert "default 'undecided'" in mig and "assignment_confirmed_at timestamptz" in mig
assert "check ((assignment_preference = 'undecided') = (assignment_confirmed_at is null))" in mig
assert "add column if not exists" in mig                                   # idempotent
roll = (ROOT / "supabase/migrations/202609240001_multi_account_options.sql").read_text()
assert "assignment_preference" not in roll                                 # rolls never copy (no inheritance)
for f in ("docs/index.html", "scripts/fetch_and_build.py"):
    t = (ROOT / f).read_text(encoding="utf-8")
    assert 'id="optAssignmentPref"' in t and '<option value="undecided">尚未决定（默认）</option>' in t, f
    assert "assignment_preference, assignment_confirmed_at, premium_chain_per_share" in t, f
    assert "assignment_preference==='undecided' ? null" in t, f              # undecided never gets a timestamp
    assert "/assignment_preference|assignment_confirmed_at/.test" in t, f   # backward compatible before migration
dep = (ROOT / ".github/workflows/deploy-supabase.yml").read_text()
assert "option_assignment_preference_audit.sql" in dep and "unconfirmed_claims" in dep
print("PASS option assignment preference contract")
