-- 0062 · Phase 9 task 6 — the join between a Google identity and an owner.
--
-- Supabase Auth answers "who signed in". It does not answer "whose queue,
-- tray, CV and budget is this request for" — that is this engine's own
-- question, and `profiles` has always been where it is answered. One column
-- joins the two: the JWT's `sub` (the Supabase auth user id), stamped on the
-- profile the door creates the first time that identity appears.
--
--   nullable — the founder and every friend-tier profile has no auth user and
--              never will. Sign-in is one way in, not the only way.
--   unique   — an identity maps to exactly one owner. This is the constraint,
--              not the read that precedes it: two first-sign-in requests
--              arriving together both find nothing and both insert, and it is
--              this index that decides which one is the profile. The loser
--              rolls back to a savepoint and re-reads (src/auth/signin.py).
--
-- No foreign key to auth.users, deliberately. A FK would either cascade —
-- deleting a person's whole owner record when their auth row goes, which the
-- keep-all rule forbids — or block the auth deletion outright. The profile is
-- OURS: it outlives the identity provider's row, and the column records where
-- the person came in from, not who owns them.
--
-- The column carries no secret: `sub` is an opaque uuid, and it is only ever
-- written after the door has verified the token's signature, issuer and
-- audience. An unverified `sub` never reaches this table.
--
-- Guard: tests/test_signin_identity.py (RUN_DB_TESTS=1) —
-- ::test_the_auth_user_column_is_unique_and_optional asserts both properties
-- against the live column, and the RLS/budget tests either side of it prove a
-- profile created this way is an owner like any other, with no new code.
BEGIN;

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS auth_user_id uuid;

CREATE UNIQUE INDEX IF NOT EXISTS profiles_auth_user_id_key
  ON public.profiles (auth_user_id);

COMMENT ON COLUMN public.profiles.auth_user_id IS
  'The Supabase Auth user id (a verified JWT''s `sub`) this profile was created for, or NULL for a friend-tier profile that has no sign-in. Written only by the MCP door after the token''s signature, issuer and audience have been verified.';

COMMIT;
