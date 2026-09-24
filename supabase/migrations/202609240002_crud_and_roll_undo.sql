-- V3.3 手工录入治理：安全撤回误录的最后一笔展期。
-- 仅允许撤回仍处于原始状态、且尚未继续操作的新仓；全程在一个事务中完成。

create or replace function public.undo_option_roll_v33(
  p_journal_id bigint
) returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_j public.option_roll_journal%rowtype;
  v_old public.options_positions%rowtype;
  v_new public.options_positions%rowtype;
  v_restored_qty integer;
  v_restored_fee numeric;
begin
  if auth.uid() is null then raise exception 'AUTH_REQUIRED'; end if;

  select * into v_j from public.option_roll_journal
  where id = p_journal_id and user_id = auth.uid() for update;
  if not found then raise exception 'ROLL_JOURNAL_NOT_FOUND'; end if;
  if v_j.old_position_id is null or v_j.new_position_id is null then
    raise exception 'ROLL_LINK_MISSING';
  end if;

  select * into v_old from public.options_positions
  where id = v_j.old_position_id and user_id = auth.uid() for update;
  select * into v_new from public.options_positions
  where id = v_j.new_position_id and user_id = auth.uid() for update;
  if v_old.id is null or v_new.id is null then raise exception 'ROLL_POSITION_NOT_FOUND'; end if;
  if coalesce(v_new.status,'open') <> 'open'
     or v_new.rolled_from_id is distinct from v_old.id
     or v_new.rolled_to_id is not null
     or coalesce(v_new.qty,0) <> coalesce(v_j.qty,0) then
    raise exception 'NEW_POSITION_ALREADY_CHANGED';
  end if;
  if exists (
    select 1 from public.option_roll_journal x
    where x.user_id = auth.uid() and x.id <> v_j.id
      and (x.old_position_id = v_new.id
        or (x.old_position_id = v_old.id and x.executed_at > v_j.executed_at))
  ) then raise exception 'LATER_ROLL_EXISTS'; end if;

  if coalesce(v_old.status,'open') = 'rolled' and v_old.rolled_to_id = v_new.id then
    update public.options_positions set
      status='open', closed_at=null, exit_price=null, close_fee=0,
      realized_pnl=null, settlement_type=null, rolled_to_id=null, close_notes=null
    where id=v_old.id;
    v_restored_qty := coalesce(v_old.qty,1);
  elsif coalesce(v_old.status,'open') = 'open' and v_old.rolled_to_id is null then
    v_restored_qty := coalesce(v_old.qty,0) + coalesce(v_j.qty,0);
    v_restored_fee := case when coalesce(v_old.qty,0) > 0
      then coalesce(v_old.open_fee,0) * v_restored_qty / v_old.qty
      else coalesce(v_old.open_fee,0) end;
    update public.options_positions set qty=v_restored_qty, open_fee=v_restored_fee
    where id=v_old.id;
  else
    raise exception 'OLD_POSITION_ALREADY_CHANGED';
  end if;

  delete from public.option_roll_journal where id=v_j.id;
  delete from public.options_positions where id=v_new.id;

  return jsonb_build_object(
    'journal_id',v_j.id,'old_position_id',v_old.id,
    'deleted_new_position_id',v_new.id,'restored_qty',v_restored_qty
  );
end;
$$;

grant execute on function public.undo_option_roll_v33(bigint) to authenticated;
