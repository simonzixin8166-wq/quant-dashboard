-- Corrective guard for option-learning state-entry semantics.
-- Suppress only unchanged consecutive states. Re-entry A -> B -> A is retained.
-- This migration cannot recreate rows already deleted by an older deployed
-- migration; production private data must be independently reconciled.

create or replace function public.option_learning_suppress_unchanged_state()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
  prior_fingerprint text;
begin
  perform pg_advisory_xact_lock(hashtext(new.user_id::text || ':' || new.position_id::text));

  select o.state_fingerprint
    into prior_fingerprint
  from public.option_learning_observations o
  where o.user_id = new.user_id
    and o.position_id = new.position_id
  order by o.observed_at desc, o.id desc
  limit 1;

  if prior_fingerprint is not null and prior_fingerprint = new.state_fingerprint then
    return null;
  end if;

  return new;
end;
$$;

drop trigger if exists option_learning_state_entry_guard
  on public.option_learning_observations;

create trigger option_learning_state_entry_guard
before insert on public.option_learning_observations
for each row execute function public.option_learning_suppress_unchanged_state();

comment on function public.option_learning_suppress_unchanged_state() is
  'Append-only learning guard: suppress unchanged consecutive option states; retain re-entry into any earlier state.';
