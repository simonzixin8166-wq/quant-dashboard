from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sql=(ROOT/"supabase/migrations/202610060002_option_learning_observations.sql").read_text(encoding="utf-8")
assert "create table if not exists public.option_learning_observations" in sql
assert "unique (user_id, position_id, state_fingerprint)" in sql
assert "alter table public.option_learning_observations enable row level security" in sql
assert "auth.uid() = user_id" in sql
for field in ["risk_level","risk_reason","dte","underlying_price","delta","spread_ratio","state_fingerprint"]:
    assert field in sql
print("PASS private option learning observation contract")

guard=(ROOT/"supabase/migrations/202610080001_option_state_entry_guard.sql").read_text(encoding="utf-8")
legacy=(ROOT/"supabase/migrations/202610060004_option_state_transition_semantics.sql").read_text(encoding="utf-8")
assert "delete from public.option_learning_observations" not in legacy.lower()
assert "option_learning_state_entry_guard" in guard
assert "prior_fingerprint = new.state_fingerprint" in guard
assert "return null" in guard.lower()
assert "pg_advisory_xact_lock" in guard
assert "retain re-entry" in guard.lower()
