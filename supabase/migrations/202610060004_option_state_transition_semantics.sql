-- Learning Quality: true option state-transition semantics.
-- Re-entry into an earlier state is allowed; only unchanged consecutive states are suppressed.

alter table public.option_learning_observations
  drop constraint if exists option_learning_observations_user_id_position_id_state_fing_key;

-- IMPORTANT: Do not collapse historical re-entry states.
-- A -> B -> A is three distinct state-entry observations. The application
-- suppresses only unchanged consecutive states; historical rows stay append-only.

create index if not exists option_learning_state_entry_idx
  on public.option_learning_observations(user_id, position_id, observed_at desc, state_fingerprint);
