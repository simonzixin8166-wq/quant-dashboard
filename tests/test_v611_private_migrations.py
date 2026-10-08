"""V6.11 private investment tables: migrations are idempotent and the USD carry-over can never
re-convert or wipe an amount; the isolation audit covers other-user and anon access."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
m2 = (ROOT / "supabase/migrations/202610080002_investment_plans_private.sql").read_text(encoding="utf-8")
m3 = (ROOT / "supabase/migrations/202610080003_dca_amount_usd.sql").read_text(encoding="utf-8")
audit = (ROOT / "supabase/tests/v611_rls_isolation.sql").read_text(encoding="utf-8")

# Idempotent DDL.
assert m2.count("create table if not exists") == 3
assert "unique (user_id, plan_month)" in m2  # one plan per user per month
assert m2.count("enable row level security") == 3
for verb in ("select", "insert", "update", "delete"):
    assert f"_owner_{verb}" in m2 and f"drop policy if exists %I on public.%I', t || '_owner_{verb}'" in m2
assert "auth.uid() = user_id" in m2 and "to anon" not in m2

# USD carry-over: only rows not yet migrated, no FX multiplication, history untouched.
updates = re.findall(r"update public\.(\w+)\s+set (.+?)\s+where (.+?);", m3, re.S)
assert {u[0] for u in updates} == {"investment_plan_settings", "dca_monthly_plans"}
for table, sets, where in updates:
    assert "is null and" in where and "is not null" in where, where  # second run is a no-op
    assert "*" not in sets and "/" not in sets  # never multiplies/divides by an FX rate
assert "investment_executions" not in m3  # recorded trades are never rewritten
assert "add column if not exists" in m3 and "delete from" not in m3.lower()

# Isolation audit: other authenticated user + anon, read and write probes, counts only.
for needle in ("set local role authenticated", "set local role anon", "RLS_LEAK", "RLS_WRITE_NOT_BLOCKED",
               "RLS_UPDATE_LEAK", "duplicate_month_plans", "executions_cross_user_or_orphan"):
    assert needle in audit, needle
assert not re.search(r"select\s+(dca_monthly_usd|amount_usd|gold_budget_usd|price_usd|shares)\b", audit)
print("PASS V6.11 private migrations idempotent + isolation audit coverage")
