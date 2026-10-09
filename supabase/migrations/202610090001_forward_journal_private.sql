-- Forward decision journal: private, append-only server copy of the browser journal (mavDecisionJournalV56).
-- Owner-only RLS. Never published into docs/. Idempotent (safe to re-run from the deploy job).
--
-- Provenance rules (enforced server-side, the client cannot set them):
--   server_received_at  = now() at insert time.
--   capture_mode        = 'live_sync'  when the server received the row before the next US session opened
--                                       after journal_date (so no outcome information could exist yet);
--                         'late_upload' otherwise (e.g. the 9/28–9/30 rows uploaded on first sync).
--   forward_attested    = (capture_mode = 'live_sync'). Only attested rows may ever count as Genuine Forward.
--   original_first_seen_at is the browser's claim and is kept verbatim, but never used for attestation.
--   content_sha         = sha256 of the jsonb payload (jsonb text is key-ordered, so it is canonical).
-- A changed intraday judgement is a new row (new content_sha); nothing is updated or deleted.

create table if not exists public.forward_journal_entries (
  user_id uuid not null default auth.uid(),
  journal_date date not null,
  symbol text not null check (symbol ~ '^[A-Z0-9.^=-]{1,16}$'),
  payload jsonb not null,
  market jsonb not null default '{}'::jsonb,
  original_first_seen_at timestamptz,
  content_sha text not null default '',
  server_received_at timestamptz not null default now(),
  capture_mode text not null default 'late_upload' check (capture_mode in ('live_sync','late_upload')),
  forward_attested boolean not null default false,
  client_version text not null default '',
  primary key (user_id, journal_date, symbol, content_sha)
);

create index if not exists forward_journal_entries_user_date_idx
  on public.forward_journal_entries (user_id, journal_date desc);

create or replace function public.forward_journal_next_open(d date)
returns timestamptz language sql immutable as $$
  -- next weekday after d at 09:30 America/New_York (holidays ignored: stricter, never looser)
  select ((d + case extract(isodow from d)::int when 5 then 3 when 6 then 2 else 1 end)::timestamp
          + interval '9 hours 30 minutes') at time zone 'America/New_York'
$$;

create or replace function public.forward_journal_stamp()
returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' or tg_op = 'DELETE' then
    raise exception 'FORWARD_JOURNAL_APPEND_ONLY';
  end if;
  new.server_received_at := now();
  new.content_sha := encode(sha256(convert_to(new.payload::text || '|' || new.market::text, 'UTF8')), 'hex');
  if now() < public.forward_journal_next_open(new.journal_date) then
    new.capture_mode := 'live_sync';
    new.forward_attested := true;
  else
    new.capture_mode := 'late_upload';
    new.forward_attested := false;
  end if;
  return new;
end $$;

drop trigger if exists forward_journal_stamp_ins on public.forward_journal_entries;
create trigger forward_journal_stamp_ins before insert on public.forward_journal_entries
  for each row execute function public.forward_journal_stamp();
drop trigger if exists forward_journal_block_mut on public.forward_journal_entries;
create trigger forward_journal_block_mut before update or delete on public.forward_journal_entries
  for each row execute function public.forward_journal_stamp();

alter table public.forward_journal_entries enable row level security;

drop policy if exists "forward_journal_owner_select" on public.forward_journal_entries;
create policy "forward_journal_owner_select" on public.forward_journal_entries
  for select using (auth.uid() = user_id);

drop policy if exists "forward_journal_owner_insert" on public.forward_journal_entries;
create policy "forward_journal_owner_insert" on public.forward_journal_entries
  for insert with check (auth.uid() = user_id);

revoke all on public.forward_journal_entries from anon;
revoke update, delete, truncate on public.forward_journal_entries from authenticated;
grant select, insert on public.forward_journal_entries to authenticated;
