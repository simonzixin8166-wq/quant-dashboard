from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sql=(ROOT/"supabase/migrations/202610060003_option_learning_outcomes.sql").read_text(encoding="utf-8")
assert "create or replace view public.option_learning_outcomes" in sql
assert "security_invoker = true" in sql
assert "option_learning_observations" in sql
assert "options_positions" in sql
assert "outcome_mature" in sql
assert "revoke select on public.option_learning_outcomes from anon" in sql
assert "grant select on public.option_learning_outcomes to authenticated" in sql
print("PASS private option learning outcome view contract")
