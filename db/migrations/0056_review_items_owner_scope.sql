-- 0056 · Phase 9 — B-GAE-017: promotion_review flags are NOT world data.
--
-- Task 1b recorded, deliberately, that review_items is world data because all
-- four kinds are "ambiguities about PUBLIC facts". Three of them are. The
-- fourth is not: a promotion_review flag's evidence is built from the owner's
-- own lens — matched_industry_codes is the intersection with THEIR
-- promotion_rules.industry_codes, min_local_jobs is THEIR threshold, and
-- matched_titles are census titles matched against THEIR target_roles. All 20
-- rows carry both. The decision was honestly recorded and its premise was
-- still wrong; the four kinds were counted and what their evidence CONTAINED
-- was not.
--
-- owner_id is NULLABLE on purpose, and that is the design rather than a
-- shortcut: NULL means "this ambiguity is about a public fact and belongs to
-- everyone" (skill_synonym, sponsor_match, company_onboard — two people
-- resolving one sponsor ambiguity once is still correct), and a value means
-- "this was derived from one person's lens". No DEFAULT, per 0054's rule.
--
-- The backfill reads the sole profile rather than naming it: there is exactly
-- one owner today, so every existing promotion_review row is his, and a
-- literal uuid in a migration would be both personal data and a lie the day
-- it changed.
BEGIN;

ALTER TABLE public.review_items
  ADD COLUMN owner_id uuid REFERENCES public.profiles(profile_id);

COMMENT ON COLUMN public.review_items.owner_id IS
  'NULL = an ambiguity about a public fact, shared by everyone. Set = derived from one owner''s lens (promotion_review) and visible only to them.';

UPDATE public.review_items
   SET owner_id = (SELECT profile_id FROM public.profiles ORDER BY created_at LIMIT 1)
 WHERE kind = 'promotion_review';

-- Idempotency has to include the owner, or the first owner to flag an
-- organisation silently suppresses everyone else's flag for it — the same
-- shape as B-GAE-018's global dedupe_key. Partial indexes because NULL is a
-- real, meaningful value here and `is not distinct from` is what add_flag
-- compares with.
CREATE UNIQUE INDEX review_items_kind_ref_owner_uidx
    ON public.review_items (kind, ref, owner_id)
 WHERE ref IS NOT NULL AND owner_id IS NOT NULL;
CREATE UNIQUE INDEX review_items_kind_ref_world_uidx
    ON public.review_items (kind, ref)
 WHERE ref IS NOT NULL AND owner_id IS NULL;

-- The policy stops being open. World flags stay shared; owned flags are the
-- owner's alone, on read AND on write, so nobody can dismiss another
-- person's flag or forge one into their queue.
DROP POLICY IF EXISTS app_world_rows ON public.review_items;
CREATE POLICY app_owner_or_world_rows ON public.review_items FOR ALL TO goal_a_app
  USING (owner_id IS NULL OR owner_id = public.app_owner())
  WITH CHECK (owner_id IS NULL OR owner_id = public.app_owner());

COMMIT;
