-- Per-contract assignment preference that the owner explicitly confirms (#133 6083661059 A).
-- The legacy column assignment_mode defaults to 'accept' and therefore cannot express "not decided".
-- New columns:
--   assignment_preference  'undecided' (default) | 'accept' | 'avoid'
--   assignment_confirmed_at  set when the owner chooses accept/avoid; NULL while undecided.
-- Rolls create new rows through record_option_roll_v32, which copies only listed columns, so a rolled
-- contract starts 'undecided' — an unconfirmed preference is never inherited.
-- Idempotent. RLS on options_positions is unchanged (owner-only); the new columns inherit it.

alter table public.options_positions
  add column if not exists assignment_preference text not null default 'undecided',
  add column if not exists assignment_confirmed_at timestamptz;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'options_positions_assignment_preference_chk') then
    alter table public.options_positions add constraint options_positions_assignment_preference_chk
      check (assignment_preference in ('undecided','accept','avoid'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'options_positions_assignment_confirmed_chk') then
    alter table public.options_positions add constraint options_positions_assignment_confirmed_chk
      check ((assignment_preference = 'undecided') = (assignment_confirmed_at is null));
  end if;
end $$;
