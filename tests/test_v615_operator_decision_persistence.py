from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sql=(ROOT/"supabase/migrations/202610060001_operator_decisions.sql").read_text(encoding="utf-8")
js=(ROOT/"docs/assets/decision-journal.js").read_text(encoding="utf-8")

assert "create table if not exists public.operator_decisions" in sql
assert "alter table public.operator_decisions enable row level security" in sql
assert "auth.uid() = user_id" in sql
assert "grant select, insert, update, delete on public.operator_decisions to authenticated" in sql
for value in ["executed","no_action","watch","deferred","unrecorded"]:
    assert value in sql
for value in ["pending","system_error","user_decision_error","data_error","market_randomness","correct_process"]:
    assert value in sql

assert "async function persistOperatorDecision" in js
assert "async function loadOperatorDecisionsRemote" in js
assert ".from('operator_decisions')" in js
assert "onConflict:'user_id,decision_date,decision,source,fingerprint'" in js
assert "persistOperatorDecision(rows[idx])" in js
assert "persistOperatorDecision(row)" in js
assert "loadOperatorDecisionsRemote()" in js
assert "localStorage.setItem(OPERATOR_KEY" in js

print("PASS private operator decision persistence contract")
