-- V3.6.0: privacy-preserving site visit counts.
-- No IP address, email, name or raw browser fingerprint is stored.
create table if not exists public.site_visits (
  id bigint generated always as identity primary key,
  visited_at timestamptz not null default now(),
  visitor_hash text not null check (visitor_hash ~ '^[0-9a-f]{64}$'),
  path text not null default '/',
  referrer_host text,
  device text not null default 'unknown' check (device in ('desktop','tablet','mobile','unknown')),
  authenticated boolean not null default false
);

create index if not exists site_visits_visited_at_idx on public.site_visits (visited_at desc);
create index if not exists site_visits_visitor_hash_idx on public.site_visits (visitor_hash, visited_at desc);

alter table public.site_visits enable row level security;
revoke all on table public.site_visits from anon, authenticated;

create or replace function public.record_site_visit_v36(
  p_visitor_hash text,
  p_path text default '/',
  p_referrer_host text default null,
  p_device text default 'unknown'
) returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_visitor_hash is null or p_visitor_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'INVALID_VISITOR_HASH';
  end if;
  if exists (
    select 1 from public.site_visits
    where visitor_hash = p_visitor_hash
      and visited_at >= date_trunc('day', now())
  ) then
    return;
  end if;
  insert into public.site_visits(visitor_hash, path, referrer_host, device, authenticated)
  values (
    p_visitor_hash,
    left(coalesce(nullif(p_path,''), '/'), 220),
    nullif(left(coalesce(p_referrer_host,''), 160), ''),
    case when p_device in ('desktop','tablet','mobile') then p_device else 'unknown' end,
    auth.uid() is not null
  );
end;
$$;

create or replace function public.get_site_visit_summary_v36(p_days integer default 30)
returns table(total_views bigint, unique_visitors bigint, last_visit timestamptz)
language plpgsql
security definer
set search_path = public
as $$
begin
  if lower(coalesce(auth.jwt() ->> 'email', '')) <> 'xxj8166@gmail.com' then
    raise exception 'ADMIN_ONLY';
  end if;
  return query
  select count(*)::bigint, count(distinct visitor_hash)::bigint, max(visited_at)
  from public.site_visits
  where visited_at >= now() - make_interval(days => greatest(1, least(coalesce(p_days,30), 365)));
end;
$$;

revoke all on function public.record_site_visit_v36(text,text,text,text) from public;
grant execute on function public.record_site_visit_v36(text,text,text,text) to anon, authenticated;
revoke all on function public.get_site_visit_summary_v36(integer) from public;
grant execute on function public.get_site_visit_summary_v36(integer) to authenticated;
