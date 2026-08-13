-- 0001_add_engine_tables.sql
-- v2 engine tables for Goal A. Applied via Supabase MCP (apply_migration: v2_add_engine_tables).
-- Kept here as the source-of-truth record.

-- my_skills: Shayan's own skills for fit/gap comparison (maintained by hand)
create table if not exists public.my_skills (
  id bigint generated always as identity primary key,
  skill text not null,
  skill_norm text generated always as (lower(regexp_replace(btrim(skill), '\s+', ' ', 'g'))) stored,
  level text,
  evidence text,
  last_updated date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.my_skills is 'Shayan''s own skills (skill, level, evidence) for fit/gap comparison. Maintained by hand.';

-- fetch_runs: one row per fetch run; enables job-rot
create table if not exists public.fetch_runs (
  run_id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  companies_attempted int not null default 0,
  roles_seen int not null default 0,
  status text not null default 'running',
  notes text
);
comment on table public.fetch_runs is 'One row per fetch run. last_seen_run on role_listings enables job-rot (close roles not seen in latest run).';

-- soc_going_rates: per-SOC-2020 going rates for the salary wall (user-supplied)
create table if not exists public.soc_going_rates (
  id bigint generated always as identity primary key,
  occupation_code text not null,
  going_rate_annual numeric,
  going_rate_hourly numeric,
  basis text not null default 'standard',
  effective_from date,
  source text,
  created_at timestamptz not null default now(),
  unique (occupation_code, basis)
);
comment on table public.soc_going_rates is 'Per-SOC-2020 going rates for the salary wall. User-supplied; must be kept current with UK immigration rules.';
create index if not exists soc_going_rates_code_idx on public.soc_going_rates (occupation_code);

-- role_listings tweaks: run-stamp (job-rot), feed status, dedupe key
alter table public.role_listings
  add column if not exists last_seen_run bigint references public.fetch_runs(run_id),
  add column if not exists feed_status text,
  add column if not exists dedupe_key text;
create unique index if not exists role_listings_dedupe_key_uidx on public.role_listings (dedupe_key);

-- security: RLS on new tables (service-role only, matching existing posture)
alter table public.my_skills enable row level security;
alter table public.fetch_runs enable row level security;
alter table public.soc_going_rates enable row level security;
