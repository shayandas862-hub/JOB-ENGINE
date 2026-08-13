-- 0041: weekly register refresh bookkeeping (Phase 7.8 task 9 — closes the
-- "register never re-downloaded" gap found 2026-08-02). Keep-all: a sponsor
-- that loses its licence is STAMPED, never deleted; every refresh writes one
-- history row, and the daily loop uses that history to self-schedule the
-- weekly re-download.
-- Applied via Supabase MCP as `register_refresh_bookkeeping` on 2026-08-02.
alter table public.licensed_sponsors
  add column if not exists licence_removed_at timestamptz;
comment on column public.licensed_sponsors.licence_removed_at is
  'This (org, route) row vanished from the published register at this refresh — licence lapsed or revoked. Cleared if it reappears. Rows are never deleted.';
create index if not exists licensed_sponsors_removed_idx
  on public.licensed_sponsors (licence_removed_at)
  where licence_removed_at is not null;

create table if not exists public.register_refreshes (
  refresh_id   bigint generated always as identity primary key,
  refreshed_at timestamptz not null default now(),
  source_file  text,
  csv_rows     int not null default 0,
  added        int not null default 0,
  removed      int not null default 0,
  re_licensed  int not null default 0
);
comment on table public.register_refreshes is
  'One row per weekly register re-download: what file, how many rows, what changed. max(refreshed_at) drives the daily loop''s --if-stale self-scheduling.';
alter table public.register_refreshes enable row level security;
