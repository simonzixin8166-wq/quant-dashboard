-- Learning Quality: true option state-transition semantics.
-- Re-entry into an earlier state is allowed; only unchanged consecutive states are suppressed.

alter table public.option_learning_observations
  drop constraint if exists option_learning_observations_user_id_position_id_state_fing_key;

with ranked as (
  select id,
         row_number() over (
           partition by user_id, position_id, risk_level, risk_reason
           order by observed_at desc, id desc
         ) as rn
  from public.option_learning_observations
)
delete from public.option_learning_observations o
using ranked r
where o.id=r.id and r.rn>1;

create index if not exists option_learning_state_entry_idx
  on public.option_learning_observations(user_id, position_id, observed_at desc, state_fingerprint);
