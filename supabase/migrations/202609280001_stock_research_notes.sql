-- V4.9.6 Private stock research cards.
-- Thesis fields are private to the signed-in owner; public pages never expose account-specific notes.

create table if not exists public.stock_research_notes (
  user_id uuid not null default auth.uid(),
  symbol text not null,
  edge text not null default '',
  thesis text not null default '',
  catalysts text not null default '',
  risks text not null default '',
  invalidation text not null default '',
  valuation_note text not null default '',
  plan text not null default '',
  next_review_date date,
  updated_at timestamptz not null default now(),
  primary key (user_id, symbol),
  constraint stock_research_symbol_format check (symbol ~ '^[A-Z0-9.-]{1,12}$')
);

alter table public.stock_research_notes enable row level security;

drop policy if exists "stock_research_owner_select" on public.stock_research_notes;
create policy "stock_research_owner_select" on public.stock_research_notes for select using (auth.uid() = user_id);
drop policy if exists "stock_research_owner_insert" on public.stock_research_notes;
create policy "stock_research_owner_insert" on public.stock_research_notes for insert with check (auth.uid() = user_id);
drop policy if exists "stock_research_owner_update" on public.stock_research_notes;
create policy "stock_research_owner_update" on public.stock_research_notes for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "stock_research_owner_delete" on public.stock_research_notes;
create policy "stock_research_owner_delete" on public.stock_research_notes for delete using (auth.uid() = user_id);
