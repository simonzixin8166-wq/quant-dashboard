-- Audit for 202610100001: columns, constraints, RLS still on, no row claims a confirmation it lacks.
-- Probe writes run inside a rolled-back subtransaction; nothing persists. Returns integrity facts only.
do $$
declare ok boolean := false;
begin
  begin
    -- 'accept' without a confirmation time must be rejected
    perform 1 from public.options_positions limit 1;
    begin
      update public.options_positions set assignment_preference = 'accept', assignment_confirmed_at = null
        where id = (select id from public.options_positions limit 1);
      if found then raise exception 'CONFIRMATION_NOT_ENFORCED'; end if;
    exception when check_violation then ok := true;
    end;
    raise exception 'PROBE_ROLLBACK';
  exception when others then
    if sqlerrm not in ('PROBE_ROLLBACK') then raise; end if;
  end;
end $$;

select
  (select count(*) from information_schema.columns where table_schema='public' and table_name='options_positions'
     and column_name in ('assignment_preference','assignment_confirmed_at'))::int as new_columns,
  (select count(*) from pg_constraint where conname in ('options_positions_assignment_preference_chk','options_positions_assignment_confirmed_chk'))::int as constraints,
  (select relrowsecurity from pg_class where oid = 'public.options_positions'::regclass) as rls_enabled,
  (select count(*) from public.options_positions where assignment_preference <> 'undecided' and assignment_confirmed_at is null)::int as unconfirmed_claims,
  (select count(*) from pg_policies where schemaname='public' and tablename='options_positions')::int as policies;
