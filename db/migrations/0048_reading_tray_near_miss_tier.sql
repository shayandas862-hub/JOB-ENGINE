-- 0048: the reading tray gains a labelled near-miss tier + a skip stamp
-- (Phase 8.5 / U7). The tray starved because sieve 2 dropped every
-- non-matching title (0 of 1,083 staged, measured 2026-08-10); non-matching
-- survivors now stage capped as staged_tier='near_miss' for the client AI
-- to accept or SKIP — and a skip is a STAMP (keep-all: removals are stamps),
-- so a skipped row never re-stages.
-- Applied via Supabase MCP as `reading_tray_near_miss_tier` on 2026-08-10.
alter table public.role_listings
  add column if not exists staged_tier text
  check (staged_tier in ('match', 'near_miss'));
comment on column public.role_listings.staged_tier is
  'Why this row is in the reading tray: ''match'' = owner title patterns hit; ''near_miss'' = stageable but title-unmatched, served labelled for the client AI to accept or skip (U7). NULL when not staged.';
alter table public.role_listings
  add column if not exists reading_skipped_at timestamptz;
comment on column public.role_listings.reading_skipped_at is
  'The client AI looked at this near-miss and passed (skip_reading). A stamped skip never re-stages; the row itself is kept, as always.';
