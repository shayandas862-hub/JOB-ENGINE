-- 0038: promotion_rules — the manual promote button becomes a per-owner rule
-- (Phase 7.8 task 4). One row per owner; titles come live from the owner's
-- target_roles at evaluation time and are deliberately NOT stored here.
-- promote_company (MCP) stays as the manual override.
-- Applied via Supabase MCP as `promotion_rules` on 2026-08-02.
create table if not exists public.promotion_rules (
  owner_id       uuid primary key,
  industry_codes text[] not null default '{}',
  min_local_jobs int  not null default 1 check (min_local_jobs >= 0),
  auto           boolean not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
comment on table public.promotion_rules is
  'Per-owner nightly promotion rule over census board_found cards: registered industry in the set + a local census job matching the owner''s target_roles + the local-jobs floor => auto-promote (via the audited promote_from_census bridge). Exactly one condition missing => capped promotion_review flag.';

alter table public.promotion_rules enable row level security;

-- Seed the founder's rule from his current criteria: the Pass-2 software
-- industry set (discover/classify.py SOFTWARE_SIC), floor 1 local job, auto on.
insert into public.promotion_rules (owner_id, industry_codes)
select profile_id,
       array['62011','62012','62020','62090','63110','63120','58210','58290',
             '26200','72190']
  from public.profiles
 order by created_at
 limit 1
on conflict (owner_id) do nothing;
