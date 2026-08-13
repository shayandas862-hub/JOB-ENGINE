-- 0034: census keeps every job — country becomes a label, not a filter.
-- Founder rule (2026-07-16): "fetch all the jobs it finds; we filter later."
-- Applied via Supabase MCP as census_jobs_is_local on 2026-07-20.

alter table public.census_jobs
  add column if not exists is_local boolean not null default false;

-- Backfill: every row stored before this migration passed the local-only
-- filter that this migration retires, so they are all local by construction.
update public.census_jobs set is_local = true;

comment on column public.census_jobs.is_local is
  'Located in the register country (UK today). Pre-0034 rows were stored under a local-only filter and are backfilled true; since 0034 every fetched job is stored and this label replaces the filter (founder rule 2026-07-16: keep everything, filter at query time).';
