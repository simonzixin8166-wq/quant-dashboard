-- 在 Supabase Dashboard → SQL Editor 中执行一次。
-- 作用：增加持仓所有者字段、启用私有读写策略，并接管已有历史持仓。

alter table public.options_positions
  add column if not exists user_id uuid references auth.users(id) default auth.uid();

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
