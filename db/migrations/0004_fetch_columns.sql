-- 0004_fetch_columns.sql
-- Applied via Supabase MCP (apply_migration: v2_fetch_columns).
-- Per-company feed health + last fetch time, and a location on each listing.

alter table public.target_companies
  add column if not exists feed_status text,
  add column if not exists last_fetched_at timestamptz;
comment on column public.target_companies.feed_status is 'Health of the last fetch for this company: ok | error | no_feed | manual.';

alter table public.role_listings
  add column if not exists location text;
