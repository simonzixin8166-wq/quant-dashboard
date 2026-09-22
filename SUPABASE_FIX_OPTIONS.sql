-- 在 Supabase Dashboard → SQL Editor 中执行一次。
-- 作用：增加持仓所有者字段、启用私有读写策略，并接管已有历史持仓。

alter table public.options_positions
  add column if not exists user_id uuid references auth.users(id) default auth.uid();

-- V2.5：合约乘数、安全的持仓生命周期与可审计的年化ROC口径。
alter table public.options_positions
  add column if not exists multiplier integer not null default 100 check (multiplier > 0),
  add column if not exists status text not null default 'open' check (status in ('open','pending_settlement','closed','expired_worthless','assigned','exercised','rolled')),
  add column if not exists opened_at timestamptz default now(),
  add column if not exists closed_at timestamptz,
  add column if not exists exit_price numeric,
  add column if not exists open_fee numeric not null default 0,
  add column if not exists close_fee numeric not null default 0,
  add column if not exists realized_pnl numeric,
  add column if not exists settlement_type text,
  add column if not exists rolled_from_id bigint references public.options_positions(id),
  add column if not exists rolled_to_id bigint references public.options_positions(id),
  add column if not exists entry_date date,
  add column if not exists collateral_mode text check (collateral_mode in ('cash_secured','naked','covered','debit')),
  add column if not exists close_notes text,
  add column if not exists settlement_stock_price numeric;

create index if not exists options_positions_user_status_expiry_idx
  on public.options_positions(user_id, status, expiry);

alter table public.options_positions enable row level security;

drop policy if exists "options_select_private" on public.options_positions;
create policy "options_select_private" on public.options_positions
for select using (
  user_id = auth.uid() or auth.jwt() ->> 'email' = 'xxj8166@gmail.com'
);

drop policy if exists "options_insert_private" on public.options_positions;
create policy "options_insert_private" on public.options_positions
for insert with check (
  user_id = auth.uid() or auth.jwt() ->> 'email' = 'xxj8166@gmail.com'
);

drop policy if exists "options_update_private" on public.options_positions;
create policy "options_update_private" on public.options_positions
for update using (
  user_id = auth.uid() or auth.jwt() ->> 'email' = 'xxj8166@gmail.com'
) with check (
  user_id = auth.uid() or auth.jwt() ->> 'email' = 'xxj8166@gmail.com'
);

drop policy if exists "options_delete_private" on public.options_positions;
create policy "options_delete_private" on public.options_positions
for delete using (
  user_id = auth.uid() or auth.jwt() ->> 'email' = 'xxj8166@gmail.com'
);

update public.options_positions p
set user_id = u.id
from auth.users u
where p.user_id is null
  and lower(u.email) = 'xxj8166@gmail.com';

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
  check (abs((tier1_pct + tier2_pct + tier3_pct) - 1) < 0.000001)
);

alter table public.strategy_budgets enable row level security;
drop policy if exists "strategy_budgets_private" on public.strategy_budgets;
create policy "strategy_budgets_private" on public.strategy_budgets
for all using (user_id = auth.uid()) with check (user_id = auth.uid());

select id, symbol, opt_type, side, strike, expiry, cost, qty, multiplier, entry_date, collateral_mode, status, realized_pnl, user_id
from public.options_positions
order by expiry;
