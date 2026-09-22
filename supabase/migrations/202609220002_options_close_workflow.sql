-- V2.8: fields required by the close / expiry / assignment workflow.
-- Safe to run more than once.
alter table public.options_positions
  add column if not exists close_notes text,
  add column if not exists settlement_stock_price numeric;

comment on column public.options_positions.close_notes is
  'Optional private note captured when a position is closed or settled.';

comment on column public.options_positions.settlement_stock_price is
  'Underlying price at assignment/exercise time, for audit only.';
