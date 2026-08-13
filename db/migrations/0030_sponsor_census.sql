-- 0030 · Phase 7.5 Task 1 — sponsor_census + census_jobs: the census sweep's tables.
--
-- One census card per unique register organisation (org_name_norm): the sweep
-- cursor plus everything the probe and the national-registry plug-in learned.
-- Country-neutral by rule (registry_*, industry_codes, local_jobs_seen, country):
-- the UK is the first dataset, not the machine's identity. census_jobs stores
-- lightweight job rows only (no JD body) keyed by the shared dedupe_key.
-- BLAST RADIUS: these two tables are the ONLY tables the sweep writes — never
-- target_companies (fetch predicate) and never review_items (flag flood).
-- RLS enabled with no policy (service-role access, the engine's posture). Additive.
-- Applied via Supabase MCP 2026-07-11; get_advisors after: only the expected
-- INFO rls_enabled_no_policy on both new tables (same as every engine table).

create table if not exists public.sponsor_census (
  org_name_norm     text primary key,
  country           text not null default 'uk',
  sponsor_id        bigint,                    -- representative licensed_sponsors.id (min per org)
  organisation_name text,
  town_city         text,
  is_skilled_worker boolean,
  rating            text,
  -- probe layer: the ATS board census
  probed_at         timestamptz,
  probe_outcome     text check (probe_outcome in
                      ('board_found','no_board','already_tracked','error')),
  ats_type          text,
  ats_token         text,
  careers_url       text,
  local_jobs_seen   int,                       -- NULL = fetch failed; 0 = fetched, none local
  total_jobs_seen   int,
  probe_error       text,
  -- registry layer: national company registry (UK = Companies House)
  registry_checked_at timestamptz,
  registry_outcome  text check (registry_outcome in
                      ('matched','ambiguous','not_found','error')),
  registry_number   text,
  registry_status   text,
  registry_type     text,
  industry_codes    text[],                    -- UK: SIC codes
  incorporated      date,
  registry_error    text,
  created_at        timestamptz not null default now()
);
comment on table public.sponsor_census is
  'One census card per unique register organisation: sweep cursor + ATS probe findings + national-registry findings. Country-neutral columns; the sweep writes only here and census_jobs, never the daily-pipeline tables.';
create index if not exists sponsor_census_probe_outcome_idx
  on public.sponsor_census (probe_outcome);

create table if not exists public.census_jobs (
  census_job_id  bigint generated always as identity primary key,
  org_name_norm  text not null references public.sponsor_census (org_name_norm)
                 on delete cascade,
  company_name   text,
  source         text,                          -- ats_type the job came from
  title          text,
  location       text,
  url            text,
  salary_text    text,
  title_match    boolean not null default false, -- keyword match vs owner role patterns (no AI)
  dedupe_key     text not null unique,           -- the SHARED fetch.feeds.dedupe_key
  seen_at        timestamptz not null default now()
);
comment on table public.census_jobs is
  'Lightweight job rows seen during the census (title/location/url/salary only — no JD body). Identity is the shared dedupe_key; promotion to daily tracking refetches with JD via the normal pipeline.';
create index if not exists census_jobs_org_idx
  on public.census_jobs (org_name_norm);

alter table public.sponsor_census enable row level security;
alter table public.census_jobs enable row level security;
