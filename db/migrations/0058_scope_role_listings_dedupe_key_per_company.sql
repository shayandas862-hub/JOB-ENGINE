-- 0058 · Phase 9 task 3 — B-GAE-018: a job advert belongs to an owner, so the
-- key that dedupes it has to as well.
--
-- The aggregator feed is SHARED. Two owners whose lenses overlap see the same
-- advert, which for a sponsor-aware engine reading one feed is the normal case
-- and not the edge one. Each owner already gets their own target_companies row
-- (task 1b), so both produce the same
-- dedupe_key(company_name, title, url) against a different company_id.
--
-- With the unique index on dedupe_key ALONE, the merge's
-- `on conflict (dedupe_key) do nothing` meant whichever owner merged the ad
-- FIRST created the listing; the second owner's identical ad fell through to
-- the fallback lookup and was handed the FIRST owner's role_id, which then got
-- stamped into their aggregator_ads.merged_role_id. The second owner silently
-- never received the job — an isolation failure, not a cosmetic one, for a
-- product whose only number is applications sent.
--
-- Scoping the key per company keeps the dedupe that matters (the same advert
-- twice for ONE owner still collapses to one row — pinned by
-- test_one_owner_still_cannot_hold_the_same_advert_twice) and drops the one
-- that was never meant to exist. Cross-company collisions were already
-- impossible in practice: company_name is an input to the key, so two
-- different orgs cannot collide. The only pair the old index could catch was
-- the same org under two owners — exactly the pair that must NOT collide.
--
-- Callers updated in the same change, all three of them: discover/merge.py
-- (conflict target + the fallback lookup), persist/fetch_rules.py (conflict
-- target) and history/events.py, whose dedupe_key -> role_id map could
-- otherwise attach one owner's event to another owner's listing.
BEGIN;

DROP INDEX public.role_listings_dedupe_key_uidx;

CREATE UNIQUE INDEX role_listings_company_dedupe_uidx
  ON public.role_listings (company_id, dedupe_key);

COMMENT ON INDEX public.role_listings_company_dedupe_uidx IS
  'One advert per company, not per world. Global uniqueness on dedupe_key alone let the first owner to merge a shared aggregator advert swallow it from every other owner (B-GAE-018, 0058).';

COMMIT;
