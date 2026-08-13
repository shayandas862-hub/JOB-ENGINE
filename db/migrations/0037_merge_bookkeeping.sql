-- 0037: merge bookkeeping on aggregator_ads (Phase 7.8 task 3 — Wire 2).
-- The ads layer stays keep-all: the merge only STAMPS outcomes here; the
-- three columns are the whole write surface. merged_role_id points at the
-- role_listings row that the ad became (merged) or was absorbed by (duplicate).
-- Applied via Supabase MCP as `merge_bookkeeping` on 2026-08-02.
alter table public.aggregator_ads
  add column if not exists merged_at timestamptz,
  add column if not exists merge_outcome text
    check (merge_outcome in ('merged','duplicate','skipped_recruiter','skipped_not_local')),
  add column if not exists merged_role_id bigint references public.role_listings(role_id);

comment on column public.aggregator_ads.merge_outcome is
  'What the merge pass decided: merged (became its own role_listings row) | duplicate (an existing listing absorbed it) | skipped_recruiter (matched org is a known SIC-78 employment agency — stays out of the queue by default) | skipped_not_local. Stamped once; never deleted.';
comment on column public.aggregator_ads.merged_role_id is
  'The role_listings row this ad became or was absorbed by (null for skips).';

-- the merge pass selects: matched, never-attempted, oldest first
create index if not exists aggregator_ads_unmerged_idx
  on public.aggregator_ads (ad_id)
  where merged_at is null and matched_org_norm is not null;
