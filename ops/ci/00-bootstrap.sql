-- ops/ci/00-bootstrap.sql — what a vanilla Postgres lacks and Supabase provides.
--
-- Applied FIRST by ops/ci/apply-schema.sh, before ops/ci/01-genesis.sql and
-- before db/migrations/*.sql. Deliberately tiny: everything that CAN come from
-- the mirrored migration log does, and the log is not edited to suit CI.
--
-- Measured, not assumed — the whole live extension list is
-- pg_stat_statements, pg_trgm, pgcrypto, plpgsql, supabase_vault, uuid-ossp,
-- and a statement-level scan of all 58 migrations found exactly two role names
-- in real DDL (goal_a_app and postgres) with every other apparent role name
-- being prose inside a COMMENT string. So:
--
--   * goal_a_app is NOT created here. Migration 0052 creates it, and creating
--     it here would make 0052 fail with "role already exists" — the lane must
--     exercise the log, not shadow it.
--   * pgcrypto is not required for gen_random_uuid(): that has been core since
--     Postgres 13, and 0018 is its only caller.
--
-- anon and authenticated ARE needed, and not for the reason a first read
-- suggests. No migration grants to them. But four RLS policies on the two
-- public-reference tables — occ_anon_read, occ_authenticated_all,
-- sponsors_anon_read, sponsors_authenticated_all — are GENESIS: created in
-- Phase 1, named in no migration, and therefore carried in 01-genesis.sql.
-- CREATE POLICY ... TO <role> requires the role to exist. NOLOGIN because
-- nothing in this codebase connects as either; they exist so that the baseline
-- can be applied at all.
CREATE ROLE anon NOLOGIN NOINHERIT;
CREATE ROLE authenticated NOLOGIN NOINHERIT;

-- pg_trgm is on live and its 31 functions show up in a public-schema function
-- census, so the lane installs it rather than letting a `%` similarity filter
-- fail as if it were a code bug. pgcrypto is on live too and digest() is
-- reachable from application SQL.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
