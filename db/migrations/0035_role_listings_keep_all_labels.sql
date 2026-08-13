-- 0035: keep-all reaches the pipeline layer (founder rule 2026-07-16:
-- "fetch all the jobs it finds; we filter later" — labels, never filters).
-- Applied via Supabase MCP as `role_listings_keep_all_labels` on 2026-07-22.
alter table public.role_listings
  add column if not exists is_local boolean not null default true,
  add column if not exists source text;

comment on column public.role_listings.is_local is
  'True when the listing location matches the owner''s target country (label, never a filter). Pre-0035 rows were UK-filtered at fetch time, so the default-true backfill is accurate.';
comment on column public.role_listings.source is
  'Feed this listing came from: greenhouse/lever/ashby/workable/workday/adzuna/reed. Backfilled from role_url domain for pre-0035 rows.';

update public.role_listings set source = case
  when role_url ilike '%greenhouse.io%'     then 'greenhouse'
  when role_url ilike '%lever.co%'          then 'lever'
  when role_url ilike '%ashbyhq.com%'       then 'ashby'
  when role_url ilike '%workable.com%'      then 'workable'
  when role_url ilike '%myworkdayjobs.com%' then 'workday'
end
where source is null;
