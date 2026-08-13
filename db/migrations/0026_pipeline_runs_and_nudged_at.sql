-- 0026 · Phase 4 Task 1/3 — the daily run's report card + the never-renudge stamp.
-- Applied via Supabase MCP 2026-07-10.

begin;

create table if not exists public.pipeline_runs (
  run_id      bigint generated always as identity primary key,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  status      text not null default 'running' check (status in ('running','ok','failed')),
  stages      jsonb    -- [{name, ok, summary, duration_s}, ...]
);
comment on table public.pipeline_runs is
  'One row per daily pipeline run: per-stage status, output summary, duration. fetch_runs remains the fetch stage''s own log.';
alter table public.pipeline_runs enable row level security;

alter table public.role_listings
  add column if not exists nudged_at timestamptz;
comment on column public.role_listings.nudged_at is
  'When this listing was included in a nudge digest. Never re-nudge: only NULL rows are eligible.';

commit;
