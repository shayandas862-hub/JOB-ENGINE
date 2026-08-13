-- 0042: deadline_source admits 'survival'.
-- The 0024 check predates the survival-deadline work (2026-08-02): the chooser
-- returns stated | survival | estimated, but the constraint only admitted the
-- first and last — the first cloud run (2026-08-09) failed on exactly this.
-- Widen the admitted set; no rows change.

alter table public.role_listings
  drop constraint if exists role_listings_deadline_source_check;

alter table public.role_listings
  add constraint role_listings_deadline_source_check
  check (deadline_source in ('stated', 'estimated', 'survival'));

comment on column public.role_listings.deadline_source is
  'How the apply-by date was set: stated (parsed from the JD, final), '
  'survival (history curves per role family, refreshed as curves fill), '
  'estimated (flat profile window fallback, refreshed nightly).';
