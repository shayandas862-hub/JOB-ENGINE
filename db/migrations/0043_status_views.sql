-- 0043: the public status page's curated views (Phase 8 task 4).
-- Same complexity-hiding contract as the dashboard (0040): src/status/ reads
-- ONLY these, pinned by test. The difference is the AUDIENCE — this surface is
-- public and unauthenticated, so the view is the privacy boundary, not the page.
--
-- DELIBERATELY ABSENT, and must stay absent:
--   * applications_total / applied_date  — per-person application facts
--   * any owner_id, owner name, profile or notification channel
--   * any salary, salary_wall or wall_basis
--   * any ats_token / dashboard token / bearer token value (booleans only)
--   * pipeline stage SUMMARY text — it carries company names and phrases like
--     "nudged 64 listing(s)", which is the owner's activity, not machine health
-- security_invoker per house rule (0009).
-- Applied via Supabase MCP as `status_views` on 2026-08-09.

-- Per-stage health of the most recent finished run: shape only, never prose.
create or replace view public.v_status_stages with (security_invoker = true) as
select o.ord::int                                        as stage_order,
       o.s->>'name'                                      as stage,
       coalesce((o.s->>'ok')::boolean, false)            as ok,
       round(coalesce((o.s->>'duration_s')::numeric, 0), 1) as duration_s
  from public.pipeline_runs pr,
       lateral jsonb_array_elements(pr.stages) with ordinality as o(s, ord)
 where pr.run_id = (select max(run_id) from public.pipeline_runs
                     where finished_at is not null);
comment on view public.v_status_stages is
  'Public status: per-stage health of the latest finished run — stage name, ok, seconds. No summary text (it names companies and owner activity).';

-- One row of person-free headline aggregates.
create or replace view public.v_status with (security_invoker = true) as
select
  (select max(finished_at) from public.pipeline_runs)                         as last_run_at,
  (select status from public.pipeline_runs where finished_at is not null
    order by run_id desc limit 1)                                             as last_run_status,
  (select count(*) from public.v_status_stages)                               as last_run_stages,
  (select count(*) from public.v_status_stages where ok)                      as last_run_stages_ok,
  (select round(sum(duration_s))::int from public.v_status_stages)            as last_run_seconds,
  (select count(*) from public.pipeline_runs where finished_at is not null)   as runs_completed,
  (select count(*) from public.role_listings)                                 as listings_tracked,
  (select count(*) from public.role_listings where role_status = 'open')      as listings_open,
  (select count(*) from public.target_companies)                              as companies_tracked,
  (select count(*) from public.target_companies where ats_token is not null)  as companies_with_boards,
  (select count(*) from public.sponsor_census)                                as census_organisations,
  (select count(*) from public.sponsor_census where ats_token is not null)    as census_boards,
  (select count(*) from public.licensed_sponsors)                             as register_rows,
  (select current_date - max(created_at)::date
     from public.licensed_sponsors)                                           as register_age_days,
  (select count(*) from public.aggregator_ads)                                as ads_collected;
comment on view public.v_status is
  'Public status: machine-health aggregates only — last run, coverage, register age. Person-free by construction; see the header of 0043 for what must never be added.';
