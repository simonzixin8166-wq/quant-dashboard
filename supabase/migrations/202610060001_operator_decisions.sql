-- Learning Quality: persist private operator decisions for auditable Decision Learning.
-- Private per-user table; never published into docs/ or public learning artifacts.

create table if not exists public.operator_decisions (
  user_id uuid not null default auth.uid(),
  decision_date date not null,
  decision text not null,
  source text not null,
  reason text not null default '',
  data_state text not null default 'unknown',
  evidence_state text not null default 'unknown',
  fingerprint text not null,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  seen_count integer not null default 1 check (seen_count >= 1),
  user_action text not null default 'unrecorded'
    check (user_action in ('executed','no_action','watch','deferred','unrecorded')),
  attribution text not null default 'pending'
    check (attribution in ('pending','system_error','user_decision_error','data_error','market_randomness','correct_process')),
  operator_note text not null default '',
  operator_updated_at timestamptz,
  primary key (user_id, decision_date, decision, source, fingerprint)
);

create index if not exists operator_decisions_user_last_seen_idx
  on public.operator_decisions (user_id, last_seen_at desc);

alter table public.operator_decisions enable row level security;

drop policy if exists "operator_decisions_owner_select" on public.operator_decisions;
create policy "operator_decisions_owner_select" on public.operator_decisions
  for select using (auth.uid() = user_id);

drop policy if exists "operator_decisions_owner_insert" on public.operator_decisions;
create policy "operator_decisions_owner_insert" on public.operator_decisions
  for insert with check (auth.uid() = user_id);

drop policy if exists "operator_decisions_owner_update" on public.operator_decisions;
create policy "operator_decisions_owner_update" on public.operator_decisions
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "operator_decisions_owner_delete" on public.operator_decisions;
create policy "operator_decisions_owner_delete" on public.operator_decisions
  for delete using (auth.uid() = user_id);

grant select, insert, update, delete on public.operator_decisions to authenticated;
