-- Learning Quality: join private option state-entry observations to final position outcomes.
-- Security-invoker preserves the underlying RLS boundary.
create or replace view public.option_learning_outcomes
with (security_invoker = true)
as
select
  o.user_id,
  o.position_id,
  o.observed_at,
  o.risk_level,
  o.risk_reason,
  o.dte,
  o.underlying_price,
  o.delta,
  o.spread_ratio,
  p.status as final_status,
  p.realized_pnl,
  p.settlement_type,
  p.closed_at,
  (p.status not in ('open','pending_settlement')) as outcome_mature
from public.option_learning_observations o
join public.options_positions p
  on p.id=o.position_id and p.user_id=o.user_id;

revoke select on public.option_learning_outcomes from anon;
grant select on public.option_learning_outcomes to authenticated;
