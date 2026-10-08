-- V6.11 private-table isolation audit. Read-only in effect: every probe write either is
-- rejected by RLS (expected) or aborts the whole statement via RAISE, so nothing persists.
-- Simulates a second authenticated user and an anonymous visitor.
do $$
declare
  t text;
  n int;
  other uuid := '00000000-0000-4000-8000-0000000000a1';
begin
  -- 1) Another authenticated user sees none of the owner's rows and cannot write as the owner.
  execute 'set local role authenticated';
  perform set_config('request.jwt.claims', json_build_object('sub', other, 'role', 'authenticated')::text, true);
  foreach t in array array['investment_plan_settings','dca_monthly_plans','investment_executions'] loop
    execute format('select count(*) from public.%I', t) into n;
    if n <> 0 then raise exception 'RLS_LEAK % visible_to_other_user=%', t, n; end if;
  end loop;
  begin
    insert into public.investment_plan_settings(user_id, dca_monthly_usd)
      select user_id, 1 from (select '00000000-0000-4000-8000-0000000000b2'::uuid as user_id) s;
    raise exception 'RLS_WRITE_NOT_BLOCKED investment_plan_settings';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.dca_monthly_plans set status = 'completed';
    get diagnostics n = row_count;
    if n <> 0 then raise exception 'RLS_UPDATE_LEAK dca_monthly_plans rows=%', n; end if;
  end;
  -- 2) Anonymous visitors see nothing.
  execute 'set local role anon';
  perform set_config('request.jwt.claims', json_build_object('role', 'anon')::text, true);
  foreach t in array array['investment_plan_settings','dca_monthly_plans','investment_executions'] loop
    begin
      execute format('select count(*) from public.%I', t) into n;
      if n <> 0 then raise exception 'RLS_LEAK % visible_to_anon=%', t, n; end if;
    exception when insufficient_privilege then null;
    end;
  end loop;
  -- Restore the privileged role so the aggregate counts below see every row (set local would
  -- otherwise keep 'anon' for the rest of the transaction and report zeros).
  execute 'reset role';
  perform set_config('request.jwt.claims', '', true);
end $$;

-- Aggregate integrity (counts only, no amounts, no ids).
select
  current_user as audited_as,
  (select count(*) from public.investment_plan_settings) as settings_rows,
  (select count(*) from public.investment_plan_settings where dca_monthly_usd is null and dca_monthly_cny is not null) as settings_unmigrated_cny,
  (select count(*) from public.dca_monthly_plans) as plan_rows,
  (select count(*) from (select user_id, plan_month from public.dca_monthly_plans group by 1,2 having count(*) > 1) d) as duplicate_month_plans,
  (select count(*) from public.dca_monthly_plans where amount_usd is null and amount_cny is not null) as plans_unmigrated_cny,
  (select count(*) from public.dca_monthly_plans where amount_usd is null) as plans_without_usd_amount,
  (select count(*) from public.investment_executions) as execution_rows,
  (select count(*) from public.investment_executions e where e.program = 'dca' and e.plan_id is not null
     and not exists (select 1 from public.dca_monthly_plans p where p.id = e.plan_id and p.user_id = e.user_id)) as executions_cross_user_or_orphan,
  (select count(*) from pg_policies where schemaname = 'public'
     and tablename in ('investment_plan_settings','dca_monthly_plans','investment_executions')) as policies;
