-- 0061 · Phase 9 task 6 — B-GAE-032: shut the door nobody opened.
--
-- Supabase publishes a PostgREST API over this database alongside the one
-- the engine actually uses. Two roles authenticate to it: `anon` (anybody
-- holding the project's publishable key) and `authenticated` (any signed-in
-- user). Measured before this migration, on 2026-08-12:
--
--   * both roles held INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES and
--     TRIGGER on all 42 relations in public — Supabase's default grants,
--     never revoked (252 write grants counting only I/U/D);
--   * two genesis-era policies, `sponsors_authenticated_all` and
--     `occ_authenticated_all` (FOR ALL USING (true) WITH CHECK (true)),
--     let those privileges through RLS on the sponsor register and the SOC
--     table. Written via the dashboard before migration 0001, when
--     "authenticated" meant nobody because Auth had no users.
--
-- Task 6 turns Google sign-in on. The moment it does, "authenticated" means
-- any stranger with a Google account, and `update licensed_sponsors ...`
-- over the REST API would rewrite the register the whole product verifies
-- against. Nothing was exploitable while sign-in was off — which is exactly
-- why this lands first.
--
-- Verified safe to revoke, three ways, before writing a line of it: no file
-- in this repo names the data API, supabase-js or the publishable key;
-- `goal-a-mcp` carries only DATABASE_URL and MCP_TOKEN; `goal-a-status`
-- carries only DATABASE_URL. Every door here is a direct Postgres
-- connection. The data API serves nothing and never has.
--
-- The anon SELECT policies are DROPPED, deliberately (decision-log
-- 2026-08-12): the register is public government data and publishing it
-- would be defensible, but publishing is an act, not a leftover. Nothing
-- reads them, and an unused read path on a table this product's truth
-- depends on is a liability with no user. If the founder ever wants a public
-- sponsor lookup, it comes back as its own migration with its own reason.
--
-- SELECT *grants* are left in place for both roles: with RLS on and no
-- policy admitting them, a grant is inert, and the accompanying guard test
-- asserts every table in public keeps RLS on — which is what makes leaving
-- them defensible rather than lazy.
--
-- Guard: tests/test_data_api_lockdown.py (RUN_DB_TESTS=1) — asserts over
-- EVERY relation and EVERY policy, not a list, because the default grants
-- apply to future tables too. All three assertions were seen red against
-- this database before this migration ran.
BEGIN;

-- 1 · the two policies that turned the grants into a live write path -------
DROP POLICY IF EXISTS sponsors_authenticated_all ON public.licensed_sponsors;
DROP POLICY IF EXISTS occ_authenticated_all      ON public.skilled_worker_occupations;

-- 2 · the two anon read policies — dropped as a decision, not as tidying ---
DROP POLICY IF EXISTS sponsors_anon_read ON public.licensed_sponsors;
DROP POLICY IF EXISTS occ_anon_read      ON public.skilled_worker_occupations;

-- 3 · the grants themselves, on everything that exists today ---------------
-- Wider than the I/U/D the bug named, and each addition earns its place:
-- TRUNCATE empties a keep-all table without touching a policy; TRIGGER lets
-- a role attach code to somebody else's writes; REFERENCES lets it pin rows
-- in place with a foreign key. PUBLIC rides along because a grant to PUBLIC
-- reaches both roles by definition — no such grant exists today, and this is
-- what stops one being added by accident.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM anon, authenticated, PUBLIC;

-- 4 · and on everything created from here on — the could-it-return half ----
-- Without this the revoke above lasts exactly until the next CREATE TABLE:
-- Supabase's default privileges re-grant everything to both roles on every
-- new relation. A default ACL belongs to the role that creates the object;
-- `postgres` is the grantor for every path that creates a table in this
-- project (Supabase MCP migrations, the SQL editor, the engine). It is
-- neither superuser nor a member of `supabase_admin`, so supabase_admin's
-- own default ACL cannot be altered from here — stated as a known limit, and
-- covered in practice because the guard test checks live grants over every
-- relation whatever created it.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLES FROM anon, authenticated, PUBLIC;

COMMIT;
