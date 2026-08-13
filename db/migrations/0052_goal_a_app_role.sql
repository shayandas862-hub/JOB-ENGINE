-- 0052 · Phase 9 task 2a — a role that CANNOT bypass row-level security.
--
-- Measured before writing this: every door in the codebase (the engine, the
-- MCP server, the dashboard, the status page) connects through one get_conn()
-- as `postgres`, and `postgres` carries rolbypassrls. RLS was therefore on
-- across 28 tables and enforcing nothing, and adding policies alone would not
-- have changed that by one row. FORCE ROW LEVEL SECURITY would not have
-- either: FORCE removes the table-OWNER exemption, not the role attribute.
--
-- So the policies in 0053 are written against this role instead. It is
-- NOLOGIN on purpose: task 2a proves refusal by assuming it with SET ROLE
-- (RLS is evaluated against current_user, so assuming a non-bypassing role is
-- enough to drop the bypass), which needs no new credential and no change to
-- DATABASE_URL. Task 2b cuts the engine over. Until then these policies
-- protect nothing in production — that is a deliberate split, not an
-- oversight.
--
-- SELECT/INSERT/UPDATE only. No DELETE, ever: keep-all tables never lose rows
-- and removals are stamps. That rule has lived in prose since Phase 1; this
-- is the first time the database holds it.
BEGIN;

CREATE ROLE goal_a_app NOLOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- postgres must be a member to SET ROLE to it (and to cut over in 2b).
GRANT goal_a_app TO postgres;

GRANT USAGE ON SCHEMA public TO goal_a_app;

-- Broad privileges, narrow policies — the Supabase pattern already in use for
-- anon/authenticated. RLS is the gate; the grant is only what makes the gate
-- reachable, so that a refusal is a REFUSAL and not a permission error.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO goal_a_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO goal_a_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO goal_a_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO goal_a_app;

COMMENT ON ROLE goal_a_app IS
  'The application role. Cannot bypass RLS, owns no table, cannot DELETE. Every request must set app.owner_id; policies fail closed when it is unset.';

COMMIT;
