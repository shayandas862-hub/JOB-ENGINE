-- 0039: the sieve-3 reading tray lives as states on role_listings
-- (Phase 7.8 task 5). No new table: staging, claiming and read quality are
-- per-listing facts, and rows upgrade IN PLACE when a verified client
-- reading is accepted.
-- Applied via Supabase MCP as `reading_queue` on 2026-08-02.
alter table public.role_listings
  add column if not exists read_quality text
    check (read_quality in ('keywords','ai')),
  add column if not exists read_provenance text,
  add column if not exists staged_at timestamptz,
  add column if not exists claimed_at timestamptz;

comment on column public.role_listings.read_quality is
  'How the current reading was produced: keywords (engine fallback) | ai (caged Gemini, or a client submission that passed the grounding gate). NULL = read before quality tracking, or never read. The tray stages anything not ''ai''.';
comment on column public.role_listings.read_provenance is
  'Who produced the current reading: keywords | gemini | a client label from submit_reading.';
comment on column public.role_listings.staged_at is
  'In the sieve-3 reading tray since (NULL = not staged). Set by reading.stage in the daily loop; cleared when a verified reading is accepted.';
comment on column public.role_listings.claimed_at is
  'Served to a client at (get_reading_batch). Stale claims re-serve after the reclaim window; cleared on accept.';

create index if not exists role_listings_reading_tray_idx
  on public.role_listings (staged_at)
  where staged_at is not null;
