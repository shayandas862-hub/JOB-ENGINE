-- 0024 · Phase 3 Task 1 — the system's memory: listing_events + content fingerprint.
--
-- Every listing gets a life story: appeared / changed (with a field-level JSON
-- diff) / closed / reopened. content_fingerprint is the change detector —
-- dedupe_key stays the identity, the fingerprint tracks content drift.
-- profiles.apply_window_days feeds the advisory apply-by estimate (Task 4).
-- Applied via Supabase MCP 2026-07-10.

begin;

alter table public.role_listings
  add column if not exists content_fingerprint text,
  add column if not exists deadline_source text
    check (deadline_source in ('stated', 'estimated'));
comment on column public.role_listings.content_fingerprint is
  'sha1 over normalised title|location|salary_text|jd hash. Change detector; dedupe_key remains the identity.';
comment on column public.role_listings.deadline_source is
  '''stated'' = parsed from the JD; ''estimated'' = advisory (first_seen + profile apply window). NULL = no deadline set.';

alter table public.profiles
  add column if not exists apply_window_days integer not null default 21;
comment on column public.profiles.apply_window_days is
  'Advisory apply-by window: estimated deadline = first_seen + this many days when no deadline is stated.';

create table if not exists public.listing_events (
  event_id    bigint generated always as identity primary key,
  role_id     bigint not null references public.role_listings(role_id) on delete cascade,
  event_type  text not null check (event_type in ('appeared', 'changed', 'closed', 'reopened')),
  occurred_at timestamptz not null default now(),
  changes     jsonb,          -- field-level diff for 'changed'; null otherwise
  run_id      bigint          -- fetch run that observed the event, when applicable
);
comment on table public.listing_events is
  'Life story of every listing: appeared/changed/closed/reopened, with field-level diffs for changes.';
create index if not exists listing_events_role_idx
  on public.listing_events (role_id, occurred_at desc);
alter table public.listing_events enable row level security;

commit;
