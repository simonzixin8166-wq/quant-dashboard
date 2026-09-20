alter table public.options_positions
  add column if not exists entry_date date,
  add column if not exists collateral_mode text
    check (collateral_mode in ('cash_secured','naked','covered','debit'));

create table if not exists public.strategy_budgets (
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  reserve_amount numeric not null default 0 check (reserve_amount >= 0),
  currency text not null default 'USD',
  tier1_pct numeric not null default 0.20,
  tier2_pct numeric not null default 0.30,
  tier3_pct numeric not null default 0.50,
  updated_at timestamptz not null default now(),
  primary key (user_id, symbol),
  check (tier1_pct >= 0 and tier2_pct >= 0 and tier3_pct >= 0),
  check (abs((tier1_pct + tier2_pct + tier3_pct) - 1) < 0.000001)
);

alter table public.strategy_budgets enable row level security;

drop policy if exists "strategy_budgets_private" on public.strategy_budgets;
create policy "strategy_budgets_private"
on public.strategy_budgets for all
using (user_id = auth.uid())
with check (user_id = auth.uid());
