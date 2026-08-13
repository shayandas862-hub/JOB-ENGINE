-- 0054 · Phase 9 task 2a — an unstamped write must fail loudly, not become
-- the founder's.
--
-- Migration 0018 gave five tables
-- `owner_id DEFAULT '00000000-0000-4000-a000-000000000001'`. With one person
-- that was a convenience; with two it is silent mis-attribution — a write
-- that forgot to say whose it was would simply become his, and nothing
-- anywhere would report it. Flagged since Phase 2, dropped here.
--
-- Safe because it was already unused: every INSERT into these five tables in
-- src/ and scripts/ was read before this migration was written, and all of
-- them pass owner_id explicitly. The default protected nothing and only stood
-- ready to hide a future mistake.
--
-- access_keys was built with no default from the start (task 1a). That is now
-- the rule for every owner-scoped table, held by
-- tests/test_owner_scoping.py::test_no_owner_scoped_table_reintroduces_a_default_owner
-- rather than by anyone remembering.
BEGIN;

ALTER TABLE public.cv_blocks        ALTER COLUMN owner_id DROP DEFAULT;
ALTER TABLE public.my_constraints   ALTER COLUMN owner_id DROP DEFAULT;
ALTER TABLE public.my_skills        ALTER COLUMN owner_id DROP DEFAULT;
ALTER TABLE public.target_companies ALTER COLUMN owner_id DROP DEFAULT;
ALTER TABLE public.target_roles     ALTER COLUMN owner_id DROP DEFAULT;

COMMIT;
