-- Negative tests for stock_positions (#133 B). All probes run in rolled-back subtransactions; nothing persists.
-- Returns integrity facts only (no row data).
do $$
declare
  n int;
  a uuid := '00000000-0000-4000-8000-0000000000a1';
  b uuid := '00000000-0000-4000-8000-0000000000b2';
  acct_a bigint; acct_b bigint;
begin
  begin
    -- fixtures (rolled back): two users, one account each (owned by these synthetic ids only inside this probe)
    insert into auth.users (id) values (a), (b) on conflict do nothing;
    insert into public.broker_accounts (user_id, name) values (a, 'probe-a') returning id into acct_a;
    insert into public.broker_accounts (user_id, name) values (b, 'probe-b') returning id into acct_b;

    execute 'set local role authenticated';
    perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
    insert into public.stock_positions (user_id, broker_account_id, symbol, shares) values (a, acct_a, 'ZZPROBE', 10);
    -- duplicate open position in the same account → rejected
    begin
      insert into public.stock_positions (user_id, broker_account_id, symbol, shares) values (a, acct_a, 'ZZPROBE', 5);
      raise exception 'DUPLICATE_NOT_BLOCKED';
    exception when unique_violation then null;
    end;
    -- attaching to another user's account → rejected by trigger
    begin
      insert into public.stock_positions (user_id, broker_account_id, symbol, shares) values (a, acct_b, 'ZZPROBE', 5);
      raise exception 'CROSS_ACCOUNT_NOT_BLOCKED';
    exception when raise_exception then
      if sqlerrm <> 'STOCK_POSITION_ACCOUNT_NOT_OWNED' then raise; end if;
    end;
    -- writing a row for another user → rejected by RLS
    begin
      insert into public.stock_positions (user_id, broker_account_id, symbol, shares) values (b, acct_b, 'ZZPROBE', 5);
      raise exception 'RLS_WRITE_NOT_BLOCKED';
    exception when insufficient_privilege then null;
    end;
    -- invalid values → rejected
    begin
      insert into public.stock_positions (user_id, broker_account_id, symbol, shares) values (a, acct_a, 'BAD SYMBOL', 0);
      raise exception 'CHECK_NOT_ENFORCED';
    exception when check_violation then null;
    end;
    -- user b sees nothing of user a
    perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
    select count(*) into n from public.stock_positions;
    if n <> 0 then raise exception 'RLS_LEAK visible_to_other_user=%', n; end if;
    update public.stock_positions set shares = 1;
    get diagnostics n = row_count;
    if n <> 0 then raise exception 'RLS_UPDATE_LEAK rows=%', n; end if;
    -- anon sees nothing
    execute 'set local role anon';
    perform set_config('request.jwt.claims', json_build_object('role', 'anon')::text, true);
    begin
      select count(*) into n from public.stock_positions;
      if n <> 0 then raise exception 'RLS_LEAK visible_to_anon=%', n; end if;
    exception when insufficient_privilege then null;
    end;
    raise exception 'PROBE_ROLLBACK';
  exception when others then
    if sqlerrm <> 'PROBE_ROLLBACK' then raise; end if;
  end;
end $$;

select current_user as audited_as,
  (select relrowsecurity from pg_class where oid = 'public.stock_positions'::regclass) as rls_enabled,
  (select count(*) from pg_policies where schemaname='public' and tablename='stock_positions')::int as policies,
  (select count(*) from public.stock_positions s join public.broker_accounts a on a.id = s.broker_account_id where a.user_id <> s.user_id)::int as cross_account_rows,
  (select count(*) from (select user_id, broker_account_id, symbol from public.stock_positions where status='open' group by 1,2,3 having count(*) > 1) d)::int as duplicate_open;
