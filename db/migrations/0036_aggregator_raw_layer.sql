-- 0036: the aggregator raw layer — keep-all ads, resume cursors, quota ledger.
-- Doctrine mirrors the census: store EVERYTHING labelled (matched or not);
-- matching is a re-runnable label pass that costs zero API quota; merging into
-- role_listings is a separate, later, deduped step. Blast radius: the
-- aggregator sweep writes ONLY these tables (plus census board hints during
-- token harvest).
-- Applied via Supabase MCP as `aggregator_raw_layer` on 2026-07-22.

create table if not exists public.aggregator_ads (
  ad_id               bigint generated always as identity primary key,
  source              text not null check (source in ('adzuna','reed')),
  external_id         text not null,
  employer_name       text not null,   -- as printed on the ad (display string)
  employer_norm       text not null,   -- shared norm() for register matching
  title               text not null,
  location            text,
  is_local            boolean not null default false,
  salary_min          numeric,
  salary_max          numeric,
  salary_text         text,
  posted_at           date,
  ad_url              text,            -- redirect/apply link (token harvest follows it)
  snippet             text,            -- short description; NOT a full JD
  matched_org_norm    text,            -- licensed_sponsors/sponsor_census org_name_norm
  match_method        text,            -- exact | suffix_stripped | none-yet
  matched_at          timestamptz,     -- attempt stamp (set with NULL org = no match)
  harvest_checked_at  timestamptz,     -- token harvest followed this ad's link
  dedupe_key          text not null unique,      -- sha1(source|external_id)
  content_fingerprint text not null,   -- sha1(employer|title|location norms) — cross-source
  first_seen          timestamptz not null default now(),
  last_seen           timestamptz not null default now()
);
comment on table public.aggregator_ads is
  'Raw keep-all layer for aggregator (Adzuna/Reed) job ads. Every ad seen is stored, matched or not — matching/harvest are label passes over stored rows and never re-spend API quota. Snippet only; full JDs come from boards after promotion.';
create index if not exists aggregator_ads_employer_idx
  on public.aggregator_ads (employer_norm);
create index if not exists aggregator_ads_fingerprint_idx
  on public.aggregator_ads (content_fingerprint);
create index if not exists aggregator_ads_matched_idx
  on public.aggregator_ads (matched_org_norm) where matched_org_norm is not null;
create index if not exists aggregator_ads_unattempted_idx
  on public.aggregator_ads (employer_norm) where matched_at is null;

create table if not exists public.aggregator_cursor (
  slice_key      text primary key,     -- e.g. 'reed|kw=|loc=' / 'adzuna|cat=it-jobs'
  source         text not null check (source in ('adzuna','reed')),
  params         jsonb not null default '{}'::jsonb,
  next_page      int not null default 1,   -- adzuna: page number; reed: page index (skip = page*take)
  total_reported int,                      -- provider's total at last call
  ads_seen       int not null default 0,
  pass_complete  boolean not null default false,
  updated_at     timestamptz not null default now()
);
comment on table public.aggregator_cursor is
  'Resume state per sweep slice: a stopped or quota-exhausted drip resumes at next_page with zero loss. pass_complete flips when a page returns empty or the total is reached.';

create table if not exists public.api_quota_ledger (
  source text not null,
  day    date not null,
  calls  int not null default 0,
  primary key (source, day)
);
comment on table public.api_quota_ledger is
  'Daily API-call budget bookkeeping per source. The sweep refuses to exceed its cap; the drip resumes after midnight without any operator action.';

alter table public.aggregator_ads    enable row level security;
alter table public.aggregator_cursor enable row level security;
alter table public.api_quota_ledger  enable row level security;
