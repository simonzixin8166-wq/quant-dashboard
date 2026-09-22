-- 目标价属于公开可读的策略参数，但只能由主理人修改。
-- 前端隐藏按钮只是交互优化，真正的写权限由这里的 RLS 保证。
alter table public.stock_targets enable row level security;

drop policy if exists "stock_targets_public_read" on public.stock_targets;
create policy "stock_targets_public_read"
on public.stock_targets for select
using (true);

drop policy if exists "stock_targets_admin_insert" on public.stock_targets;
create policy "stock_targets_admin_insert"
on public.stock_targets for insert
with check (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com');

drop policy if exists "stock_targets_admin_update" on public.stock_targets;
create policy "stock_targets_admin_update"
on public.stock_targets for update
using (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com')
with check (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com');

drop policy if exists "stock_targets_admin_delete" on public.stock_targets;
create policy "stock_targets_admin_delete"
on public.stock_targets for delete
using (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com');
