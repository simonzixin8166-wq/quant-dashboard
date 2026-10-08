-- V6.11 Investment Watch: private gold budget + monthly ETF DCA plans and executions.
-- Owner-only RLS. Never published into docs/. Idempotent: safe to re-run.

create table if not exists public.investment_plan_settings (
  user_id uuid primary key default auth.uid(),
  gold_budget_usd numeric check (gold_budget_usd is null or gold_budget_usd >= 0),
  dca_enabled boolean not null default true,
  dca_monthly_cny numeric check (dca_monthly_cny is null or dca_monthly_cny >= 0),
  dca_weights jsonb not null default '{"QQQM":0.4,"QLD":0.2,"VGT":0.4}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.dca_monthly_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  plan_month date not null,
  amount_cny numeric not null check (amount_cny >= 0),
  weights jsonb not null,
  due_date date,
  window_end date,
  status text not null default 'pending' check (status in ('pending','partial','completed','skipped')),
  status_note text not null default '',
  status_updated_at timestamptz,
  notified_events text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (user_id, plan_month)
);

create table if not exists public.investment_executions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  program text not null check (program in ('dca','gold')),
  plan_id uuid references public.dca_monthly_plans(id) on delete set null,
  gold_stage integer check (gold_stage is null or gold_stage between 1 and 4),
  gold_signal_id text,
  symbol text not null,
  shares numeric not null check (shares > 0),
  price_usd numeric not null check (price_usd > 0),
  fee_usd numeric not null default 0 check (fee_usd >= 0),
  usdcny numeric check (usdcny is null or usdcny > 0),
  executed_at date not null default current_date,
  note text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists investment_executions_user_idx on public.investment_executions (user_id, executed_at desc);
create index if not exists dca_monthly_plans_user_idx on public.dca_monthly_plans (user_id, plan_month desc);

alter table public.investment_plan_settings enable row level security;
alter table public.dca_monthly_plans enable row level security;
alter table public.investment_executions enable row level security;

do $$
declare t text;
begin
  foreach t in array array['investment_plan_settings','dca_monthly_plans','investment_executions'] loop
    execute format('drop policy if exists %I on public.%I', t || '_owner_select', t);
    execute format('create policy %I on public.%I for select using (auth.uid() = user_id)', t || '_owner_select', t);
    execute format('drop policy if exists %I on public.%I', t || '_owner_insert', t);
    execute format('create policy %I on public.%I for insert with check (auth.uid() = user_id)', t || '_owner_insert', t);
    execute format('drop policy if exists %I on public.%I', t || '_owner_update', t);
    execute format('create policy %I on public.%I for update using (auth.uid() = user_id) with check (auth.uid() = user_id)', t || '_owner_update', t);
    execute format('drop policy if exists %I on public.%I', t || '_owner_delete', t);
    execute format('create policy %I on public.%I for delete using (auth.uid() = user_id)', t || '_owner_delete', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;

comment on table public.investment_plan_settings is 'V6.11 private gold budget / monthly DCA settings (owner-only RLS).';
comment on table public.dca_monthly_plans is 'V6.11 one DCA plan per user per month (unique), reminder de-dup state.';
comment on table public.investment_executions is 'V6.11 manual DCA / gold stage executions recorded by the owner. No automatic orders.';
