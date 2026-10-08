-- V6.11 fix: the monthly DCA amount is denominated in USD (owner confirmed 2026-10-08), not CNY.
-- Idempotent. Values the owner already entered are carried over as USD.

alter table public.investment_plan_settings add column if not exists dca_monthly_usd numeric
  check (dca_monthly_usd is null or dca_monthly_usd >= 0);
alter table public.dca_monthly_plans add column if not exists amount_usd numeric
  check (amount_usd is null or amount_usd >= 0);
alter table public.dca_monthly_plans alter column amount_cny drop not null;

update public.investment_plan_settings
   set dca_monthly_usd = dca_monthly_cny, dca_monthly_cny = null
 where dca_monthly_usd is null and dca_monthly_cny is not null;
update public.dca_monthly_plans
   set amount_usd = amount_cny, amount_cny = null
 where amount_usd is null and amount_cny is not null;

comment on column public.investment_plan_settings.dca_monthly_cny is 'Deprecated (V6.11 fix): DCA amount is USD; see dca_monthly_usd.';
comment on column public.dca_monthly_plans.amount_cny is 'Deprecated (V6.11 fix): see amount_usd.';

notify pgrst, 'reload schema';
