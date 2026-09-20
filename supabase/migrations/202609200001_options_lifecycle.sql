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
