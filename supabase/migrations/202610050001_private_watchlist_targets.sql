-- V6.15 P0 privacy hardening.
-- Safe first step: stop anonymous reads of personal watchlist/strategy targets.
-- Existing owner write policies are left intact to avoid locking out the current owner
-- until app_metadata.myalpha_role='owner' is provisioned and verified.

alter table public.stock_watchlist enable row level security;
drop policy if exists "stock_watchlist_public_read" on public.stock_watchlist;
drop policy if exists "stock_watchlist_authenticated_read" on public.stock_watchlist;
create policy "stock_watchlist_authenticated_read"
on public.stock_watchlist for select
using (auth.uid() is not null);

alter table public.stock_targets enable row level security;
drop policy if exists "stock_targets_public_read" on public.stock_targets;
drop policy if exists "stock_targets_authenticated_read" on public.stock_targets;
create policy "stock_targets_authenticated_read"
on public.stock_targets for select
using (auth.uid() is not null);

comment on table public.stock_watchlist is
  'Private authenticated watchlist. Owner-write role migration follows only after owner role is provisioned.';
comment on table public.stock_targets is
  'Private authenticated strategy targets. Owner-write role migration follows only after owner role is provisioned.';
