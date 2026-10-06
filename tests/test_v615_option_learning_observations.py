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
