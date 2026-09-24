-- V3.4 可维护个股观察池。
-- 观察池公开可读，只有主理人账号可以新增、修改或删除。

create table if not exists public.stock_watchlist (
  symbol text primary key,
  display_name text not null,
  sort_order integer not null default 100,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint stock_watchlist_symbol_format check (symbol ~ '^[A-Z0-9.-]{1,12}$')
);

alter table public.stock_watchlist enable row level security;

drop policy if exists "stock_watchlist_public_read" on public.stock_watchlist;
create policy "stock_watchlist_public_read"
on public.stock_watchlist for select
using (true);

drop policy if exists "stock_watchlist_admin_insert" on public.stock_watchlist;
create policy "stock_watchlist_admin_insert"
on public.stock_watchlist for insert
with check (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com');

drop policy if exists "stock_watchlist_admin_update" on public.stock_watchlist;
create policy "stock_watchlist_admin_update"
on public.stock_watchlist for update
using (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com')
with check (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com');

drop policy if exists "stock_watchlist_admin_delete" on public.stock_watchlist;
create policy "stock_watchlist_admin_delete"
on public.stock_watchlist for delete
using (lower(auth.jwt() ->> 'email') = 'xxj8166@gmail.com');

insert into public.stock_watchlist(symbol, display_name, sort_order) values
  ('SOFI','SoFi Technologies',10), ('IREN','Iris Energy',20), ('ORCL','甲骨文',30),
  ('TSLA','特斯拉',40), ('NVDA','英伟达',50), ('TSM','台积电',60),
  ('LITE','Lumentum',70), ('AVGO','博通',80), ('MRVL','美满电子',90),
  ('NBIS','Nebius',100), ('GOOG','谷歌',110), ('AMD','超威半导体',120),
  ('HOOD','Robinhood',130), ('DRAM','Roundhill内存芯片',140), ('SPCX','SpaceX代币化',150),
  ('QQQM','纳指100(QQQM)',160), ('QLD','纳指2倍做多(QLD)',170),
  ('VGT','信息技术ETF(VGT)',180), ('QQQ','纳指100(QQQ)',190), ('VOO','标普500(VOO)',200)
on conflict (symbol) do nothing;

