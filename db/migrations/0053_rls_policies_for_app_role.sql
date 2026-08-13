-- 0053 · Phase 9 task 2a — policies on all 28 tables, for the role that
-- cannot bypass them.
--
-- Three shapes, chosen per table by where its owner actually lives:
--   * owner-scoped  — the table carries owner_id; compare it to the caller.
--   * derived       — no owner column; walk to target_companies, the same
--                     seam task 1b proved in the application layer.
--   * world         — the census, the register, the shared ledgers and the
--                     machine's own health. Not anybody's, so readable by
--                     every caller. Getting THIS half wrong is the quiet
--                     failure: RLS on with no policy denies everything, so
--                     the nightly run would report all-stages-ok having seen
--                     an empty census.
--
-- The caller is a per-request setting, not a JWT claim, because friend-tier
-- keys are database rows and not JWTs (task 1a). One function reads it, and
-- it fails CLOSED: unset or blank yields NULL, NULL never equals an owner_id,
-- so a request that forgot to say who it is for sees nothing rather than
-- everything.
--
-- Verified after applying: 28/28 tables carry a policy; get_advisors' 24
-- rls_enabled_no_policy findings are gone; a stranger reading the founder's
-- real rows as goal_a_app gets zero from every scoped table while the founder
-- gets his own; and a deliberately loosened policy was watched turning that
-- proof red before it was trusted.
BEGIN;

CREATE OR REPLACE FUNCTION public.app_owner() RETURNS uuid
  LANGUAGE sql STABLE
  SET search_path = ''
AS $$ SELECT nullif(current_setting('app.owner_id', true), '')::uuid $$;

COMMENT ON FUNCTION public.app_owner() IS
  'The owner this request is for, from the app.owner_id setting. NULL when unset — policies then match nothing, which is the intended default.';

GRANT EXECUTE ON FUNCTION public.app_owner() TO goal_a_app;

-- 1 · tables carrying owner_id ------------------------------------------
-- access_keys is included, which creates a bootstrap the cutover must solve:
-- the door resolves a presented key to an owner BEFORE it knows the owner, so
-- that ONE lookup cannot run under this policy. Task 2b runs it before
-- assuming the role (or behind a SECURITY DEFINER function) — it must not be
-- solved by loosening this policy.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'access_keys', 'cv_blocks', 'my_constraints', 'my_skills',
    'promotion_rules', 'target_companies', 'target_roles'
  ] LOOP
    EXECUTE format(
      'CREATE POLICY app_owner_rows ON public.%I FOR ALL TO goal_a_app '
      'USING (owner_id = public.app_owner()) '
      'WITH CHECK (owner_id = public.app_owner())', t);
  END LOOP;
END $$;

-- 2 · the caller's own profile row --------------------------------------
-- Also a bootstrap: default_profile_id() is the stdio/local fallback and
-- reads profiles before any owner is known. Same rule as access_keys.
CREATE POLICY app_owner_rows ON public.profiles FOR ALL TO goal_a_app
  USING (profile_id = public.app_owner())
  WITH CHECK (profile_id = public.app_owner());

-- 3 · tables that reach an owner through target_companies ---------------
CREATE POLICY app_owner_rows ON public.role_listings FOR ALL TO goal_a_app
  USING (EXISTS (SELECT 1 FROM public.target_companies c
                  WHERE c.company_id = role_listings.company_id
                    AND c.owner_id = public.app_owner()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.target_companies c
                       WHERE c.company_id = role_listings.company_id
                         AND c.owner_id = public.app_owner()));

CREATE POLICY app_owner_rows ON public.listing_events FOR ALL TO goal_a_app
  USING (EXISTS (SELECT 1 FROM public.role_listings r
                   JOIN public.target_companies c ON c.company_id = r.company_id
                  WHERE r.role_id = listing_events.role_id
                    AND c.owner_id = public.app_owner()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.role_listings r
                        JOIN public.target_companies c ON c.company_id = r.company_id
                       WHERE r.role_id = listing_events.role_id
                         AND c.owner_id = public.app_owner()));

CREATE POLICY app_owner_rows ON public.role_skills FOR ALL TO goal_a_app
  USING (EXISTS (SELECT 1 FROM public.role_listings r
                   JOIN public.target_companies c ON c.company_id = r.company_id
                  WHERE r.role_id = role_skills.role_id
                    AND c.owner_id = public.app_owner()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.role_listings r
                        JOIN public.target_companies c ON c.company_id = r.company_id
                       WHERE r.role_id = role_skills.role_id
                         AND c.owner_id = public.app_owner()));

-- 4 · world data --------------------------------------------------------
-- Shared facts and machine health. No owner to compare against, so the
-- policy is open TO THIS ROLE ONLY — anon and authenticated are unaffected
-- and still see nothing here. DELETE is impossible regardless: the role was
-- never granted it (keep-all tables lose no rows).
--
-- review_items and pipeline_runs are on this list by the decision recorded in
-- task 1b, not by omission: review flags are ambiguities about PUBLIC facts,
-- and pipeline_runs carries only stage names, durations and counts — the same
-- class the public status page already publishes. mcp_audit has no owner
-- column and so cannot be scoped here; giving it one is task 3's business.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'aggregator_ads', 'aggregator_cursor', 'api_quota_ledger', 'census_jobs',
    'cowork_findings', 'decisions', 'fetch_runs', 'licensed_sponsors',
    'mcp_audit', 'pipeline_runs', 'register_refreshes', 'review_items',
    'sic_codes', 'skill_synonyms', 'skilled_worker_occupations',
    'soc_going_rates', 'sponsor_census'
  ] LOOP
    EXECUTE format(
      'CREATE POLICY app_world_rows ON public.%I FOR ALL TO goal_a_app '
      'USING (true) WITH CHECK (true)', t);
  END LOOP;
END $$;

-- 5 · close a pre-existing exposure -------------------------------------
-- target_roles held `qual = true` policies for anon and authenticated, from
-- a single-user phase. Supabase treats the anon key as public, and
-- target_roles is per-owner personal data (what this person is looking for),
-- so anyone holding that key could read it and any signed-in user could
-- rewrite it. Nothing in the codebase uses either role — measured — so both
-- are dropped rather than narrowed. The equivalent policies on
-- licensed_sponsors, skilled_worker_occupations and decisions are LEFT
-- ALONE: those are public reference data, and something outside this repo
-- may read them. Task 6 revisits `authenticated` deliberately when sign-in
-- makes that role real.
DROP POLICY IF EXISTS target_roles_anon_read ON public.target_roles;
DROP POLICY IF EXISTS target_roles_authenticated_all ON public.target_roles;

COMMIT;
