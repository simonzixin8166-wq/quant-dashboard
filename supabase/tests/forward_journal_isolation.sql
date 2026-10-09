-- Forward journal audit: owner isolation, append-only, server-side attestation.
-- Every probe write is rejected (expected) or aborts via RAISE inside a subtransaction that is rolled
-- back, so nothing persists. Final SELECT returns integrity checks only (no row data).
do $$
declare
  n int;
  other uuid := '00000000-0000-4000-8000-0000000000a1';
  probe uuid := '00000000-0000-4000-8000-0000000000c3';
begin
  -- 1) Another authenticated user sees no rows and cannot insert as someone else.
  execute 'set local role authenticated';
  perform set_config('request.jwt.claims', json_build_object('sub', other, 'role', 'authenticated')::text, true);
  select count(*) into n from public.forward_journal_entries;
  if n <> 0 then raise exception 'RLS_LEAK forward_journal visible_to_other_user=%', n; end if;
  begin
    insert into public.forward_journal_entries(user_id, journal_date, symbol, payload)
      values ('00000000-0000-4000-8000-0000000000b2', current_date, 'ZZTEST', '{}'::jsonb);
    raise exception 'RLS_WRITE_NOT_BLOCKED forward_journal';
  exception when insufficient_privilege then null;
  end;
  -- 2) Own insert: server stamps provenance; a back-dated row is never attested; update/delete blocked.
  perform set_config('request.jwt.claims', json_build_object('sub', probe, 'role', 'authenticated')::text, true);
  begin
    insert into public.forward_journal_entries(user_id, journal_date, symbol, payload, capture_mode, forward_attested, server_received_at, original_first_seen_at)
      values (probe, current_date - 30, 'ZZTEST', '{"decision":"WATCH"}'::jsonb, 'live_sync', true, '2000-01-01', now() - interval '30 days');
    select count(*) into n from public.forward_journal_entries
      where user_id = probe and capture_mode = 'late_upload' and forward_attested = false and server_received_at > now() - interval '1 minute';
    if n <> 1 then raise exception 'ATTESTATION_NOT_SERVER_SIDE n=%', n; end if;
    begin
      update public.forward_journal_entries set symbol = 'ZZOTHER' where user_id = probe;
      get diagnostics n = row_count;
      if n <> 0 then raise exception 'APPEND_ONLY_UPDATE_LEAK rows=%', n; end if;
    exception when insufficient_privilege then null;
    end;
    begin
      delete from public.forward_journal_entries where user_id = probe;
      get diagnostics n = row_count;
      if n <> 0 then raise exception 'APPEND_ONLY_DELETE_LEAK rows=%', n; end if;
    exception when insufficient_privilege then null;
    end;
    raise exception 'PROBE_ROLLBACK';
  exception when others then
    if sqlerrm <> 'PROBE_ROLLBACK' then raise; end if;
  end;
  -- 3) Anonymous visitors see nothing.
  execute 'set local role anon';
  perform set_config('request.jwt.claims', json_build_object('role', 'anon')::text, true);
  begin
    select count(*) into n from public.forward_journal_entries;
    if n <> 0 then raise exception 'RLS_LEAK forward_journal visible_to_anon=%', n; end if;
  exception when insufficient_privilege then null;
  end;
  execute 'reset role';
end $$;

select current_user as audited_as,
  (select count(*) from public.forward_journal_entries where forward_attested and capture_mode <> 'live_sync')::int as attested_not_live,
  (select count(*) from public.forward_journal_entries where content_sha = '')::int as missing_sha,
  (select count(*) from pg_policies where schemaname = 'public' and tablename = 'forward_journal_entries')::int as policies,
  (select count(*) from pg_trigger where tgrelid = 'public.forward_journal_entries'::regclass and not tgisinternal)::int as triggers;
