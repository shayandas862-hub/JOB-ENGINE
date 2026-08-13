-- 0057 · Phase 9 task 2b — the ONE delete the app role is allowed, and why.
--
-- 0052 gave goal_a_app SELECT/INSERT/UPDATE and said "no DELETE, ever", so
-- that "keep-all tables never lose rows" stopped being prose and became a
-- privilege. Cutting the MCP door over to that role in 2b then broke exactly
-- one tool: submit_reading -> reading.accept.accept_reading runs
--     delete from role_skills where role_id = %s
-- and died with InsufficientPrivilege. Green suite, dead tool (B-GAE-023) —
-- no fake cursor enforces a privilege, so nothing in the repo could see it.
--
-- The founder's call (2026-08-11): grant DELETE on this one table rather than
-- weaken the rule everywhere or restructure the engine for a security
-- refactor. role_skills is DERIVED — accept.py's own comment calls the write
-- "the upgrade, not an accumulation", and every row is rebuilt from the job
-- description on each read. It is not a keep-all table and never was; the
-- rule was written for the tables that hold facts, and this narrows it to
-- them rather than loosening it.
--
-- Deliberately NOT added to the ALTER DEFAULT PRIVILEGES in 0052: a table
-- created tomorrow must not inherit a delete grant by accident. The other 27
-- tables keep no DELETE at all, and
-- tests/test_rls_cutover.py::test_the_app_role_holds_every_privilege_the_engine_actually_uses
-- now scans src/ for every table/verb the engine issues and fails if the role
-- cannot run one -- which is the guard that would have caught B-GAE-023
-- before the cutover instead of during it.
BEGIN;

GRANT DELETE ON public.role_skills TO goal_a_app;

COMMENT ON TABLE public.role_skills IS
  'Skills derived from a listing''s job description. Rebuilt on every read: accept_reading replaces the whole set per role_id, which is why goal_a_app holds DELETE here and on no other table (0057).';

COMMIT;
