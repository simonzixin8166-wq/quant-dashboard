-- 在 Supabase Dashboard → SQL Editor 中执行一次。
-- 作用：增加持仓所有者字段、启用私有读写策略，并接管已有历史持仓。

alter table public.options_positions
  add column if not exists user_id uuid references auth.users(id) default auth.uid();

-- V2.2：合约乘数与安全的持仓生命周期。
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
  add column if not exists rolled_to_id bigint references public.options_positions(id);

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

select id, symbol, opt_type, side, strike, expiry, cost, qty, user_id
from public.options_positions
order by expiry;
