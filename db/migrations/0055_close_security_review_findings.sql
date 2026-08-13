-- 0055 · Phase 9 task 2a — three holes the adversarial security review found
-- in 0053, closed in the same sitting.
--
-- 1 · `decisions` was left open to anon and authenticated on a false premise.
--     0053 dropped target_roles' `qual = true` policies as personal data and
--     called licensed_sponsors, skilled_worker_occupations AND decisions
--     "public reference data". The first two are. `decisions` is not: it holds
--     the founder's private strategic decision log mirrored from Notion —
--     situation summaries, predictions, outcomes and live workspace URLs.
--     Supabase treats the anon key as non-secret and task 6 of this very phase
--     ships it into a browser for the sign-in button, at which point
--     GET /rest/v1/decisions returns the lot; `decisions_authenticated_all` is
--     ALL with check true, so any signed-in user could also rewrite it.
--     Nothing in this codebase uses either role, so both are dropped.
--
-- 2 · `mcp_audit` carried USING (true) WITH CHECK (true) on the world list.
--     It has no owner column, so it could not be scoped — but it accumulates
--     every tool's verbatim arguments and results across all owners, which
--     makes it the highest-value table in the schema. No tool reads it today,
--     so the only guard was that absence. It becomes write-only for the app
--     role: the engine writes as postgres and is unaffected, and the latent
--     read is gone before task 7's runbook work adds one.
--
-- 3 · `target_roles_search_title_key` was UNIQUE on the title alone
--     (B-GAE-010). Under 0053's owner-scoped policy that is worse than a
--     collision: unique enforcement runs BELOW RLS, so after cutover a second
--     user inserting a title the founder already holds gets a duplicate-key
--     error for a row RLS says does not exist — enumerating his target list
--     one guess at a time, through the ordinary onboarding tool, with an error
--     that reads like a bug. Fixed before task 4 writes the first INSERT.
BEGIN;

DROP POLICY IF EXISTS decisions_anon_read ON public.decisions;
DROP POLICY IF EXISTS decisions_authenticated_all ON public.decisions;

DROP POLICY IF EXISTS app_world_rows ON public.mcp_audit;
CREATE POLICY app_append_only ON public.mcp_audit FOR ALL TO goal_a_app
  USING (false) WITH CHECK (true);

ALTER TABLE public.target_roles DROP CONSTRAINT target_roles_search_title_key;
ALTER TABLE public.target_roles
  ADD CONSTRAINT target_roles_owner_search_title_key
  UNIQUE (owner_id, search_title);

COMMIT;
