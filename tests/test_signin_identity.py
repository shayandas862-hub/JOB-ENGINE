"""A Google identity becomes an owner of this engine (Phase 9 task 6, step 2).

Supabase Auth answers "who signed in"; it says nothing about whose queue,
tray, CV and budget the request is for. `auth.signin.owner_for_auth_user` is
the one place the two are joined: the JWT's `sub` maps to a `profiles` row
through the new `auth_user_id` column, and on FIRST sight that row is created.

Three properties, and each is a way this could go wrong:

* **The provider's id is never the owner id.** `sub` is a foreign identifier
  handed to us by somebody else's system. Using it as our primary key would
  make every downstream row depend on the identity provider's choices.
* **First sight creates exactly once.** Two requests arriving together must
  produce one profile, not two — the unique constraint decides, not the read
  that preceded it.
* **Nothing new is needed downstream.** A JWT-born owner is an owner: RLS
  scopes it and the budget gate meters it with no new code at all. The last
  two are asserted against the real database rather than assumed, because
  "it should just work" is exactly the claim that turns out to be false.
"""
from __future__ import annotations

import os
import uuid

import pytest

from tests.conftest import FakeCursor
from tests.test_criteria import RoutingCursor

db_tests = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

SUB = "77777777-7777-4777-a777-777777777777"
EXISTING = "88888888-8888-4888-a888-888888888888"

# B-GAE-048: creating a profile for a stranger is gated now, and the gate
# defaults to SHUT. Every test below that exercises the CREATION path has to
# say so out loud, because the behaviour it describes — a first sign-in mints
# an owner — is real only when the founder has opened registration. The tests
# that merely RESOLVE a known identity deliberately do NOT pass this: that
# path is ungated, and passing it here would hide a regression where closing
# the gate locked out the owners already inside.
OPEN = {"SELF_SERVE_SIGNUP": "1"}


def test_a_known_auth_user_maps_to_their_existing_profile():
    from auth.signin import owner_for_auth_user
    cur = RoutingCursor([("from profiles", [{"profile_id": EXISTING}])])
    owner, created = owner_for_auth_user(cur, SUB, email="sam@example.com")

    assert owner == EXISTING and created is False
    assert not any("insert" in sql for sql, _ in cur.executed), \
        "an existing user was signed in and got a second profile"
    lookup = [(s, p) for s, p in cur.executed if "auth_user_id" in s]
    assert lookup and SUB in tuple(lookup[0][1])


def test_first_sign_in_creates_the_profile_and_says_so():
    from auth.signin import owner_for_auth_user
    # no row found, then the insert
    cur = RoutingCursor([("insert into profiles", [])])
    owner, created = owner_for_auth_user(cur, SUB, email="new@example.com", env=OPEN)

    assert created is True
    uuid.UUID(owner)                      # our own id, minted here
    assert owner != SUB, "the provider's subject was used as the owner id"
    insert = [(s, p) for s, p in cur.executed if "insert into profiles" in s]
    assert len(insert) == 1
    params = tuple(insert[0][1])
    assert owner in params and SUB in params, \
        "the new row must carry both our id and the identity it came from"


def test_the_new_profile_carries_no_secret_and_no_invented_name():
    # A profile is created by a stranger's first request. Everything on it
    # comes from the verified token or from nowhere: no channel, no Notion
    # ref, no default lens. The owner sets those themselves, later.
    from auth.signin import owner_for_auth_user
    cur = RoutingCursor([("insert into profiles", [])])
    owner_for_auth_user(cur, SUB, email="sam@example.com", env=OPEN)
    insert = next(p for s, p in cur.executed if "insert into profiles" in s)
    assert "sam@example.com" in tuple(insert)
    for sql, _ in cur.executed:
        assert "notification_channel" not in sql
        assert "notion_token_ref" not in sql


def test_a_sign_in_without_an_email_claim_still_gets_a_profile():
    # Google always sends one; the door must not fall over if a provider
    # or a project setting ever does not.
    from auth.signin import owner_for_auth_user
    cur = RoutingCursor([("insert into profiles", [])])
    owner, created = owner_for_auth_user(cur, SUB, email=None, env=OPEN)
    assert created is True and uuid.UUID(owner)


def test_two_first_sign_ins_at_once_resolve_to_one_profile():
    # The race the unique constraint exists for: both requests read "no such
    # user", both insert, one loses. The loser must come back with the
    # winner's profile — not an error, and not a second identity.
    import psycopg

    from auth.signin import owner_for_auth_user

    class LosesTheRace(FakeCursor):
        def __init__(self):
            super().__init__(rows=[])
            self.attempted = 0

        def execute(self, sql, params=None):
            super().execute(sql, params)
            squashed = " ".join(sql.split()).lower()
            if "insert into profiles" in squashed:
                self.attempted += 1
                raise psycopg.errors.UniqueViolation("duplicate auth_user_id")
            if "from profiles" in squashed:
                # empty the first time (the read that starts the race),
                # then the winner's row once the insert has failed
                self._rows = ([{"profile_id": EXISTING}] if self.attempted
                              else [])

    cur = LosesTheRace()
    owner, created = owner_for_auth_user(cur, SUB, email="race@example.com", env=OPEN)
    assert owner == EXISTING, "the losing request minted a second identity"
    assert created is False
    assert any("rollback to savepoint" in s for s, _ in cur.executed), \
        "a failed insert left the transaction aborted for everything after it"


# --- against the real database -------------------------------------------

@db_tests
def test_a_jwt_born_owner_is_scoped_by_rls_like_any_other():
    # The "zero new code" claim, checked rather than assumed. If the profile
    # created at sign-in were somehow special — a NULL owner, a different
    # column, a row the policies do not match — this is where it shows.
    from auth.signin import owner_for_auth_user
    from db.connection import get_conn

    sub = str(uuid.uuid4())
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner, created = owner_for_auth_user(
                    cur, sub, email="rls-probe@example.invalid", env=OPEN)
                assert created is True

                # the founder's own rows exist and are somebody else's
                cur.execute("select count(*) as n from target_companies")
                everything = cur.fetchone()["n"]

                cur.execute("set local role goal_a_app")
                cur.execute("select set_config('app.owner_id', %s, true)",
                            (owner,))
                cur.execute("select count(*) as n from target_companies")
                stranger_sees = cur.fetchone()["n"]
                cur.execute("select count(*) as n from profiles")
                own_profile = cur.fetchone()["n"]
                cur.execute("reset role")

            assert everything > 0, "no companies at all — this proves nothing"
            assert stranger_sees == 0, \
                "a freshly signed-in stranger can read the founder's companies"
            assert own_profile == 1, \
                "the new owner cannot even see their own profile row"
        finally:
            conn.rollback()


@db_tests
def test_the_budget_gate_meters_a_jwt_born_owner_with_no_new_code():
    # Task 5's per-owner budget keys on owner_id and nothing else, so a
    # sign-in owner should be metered the moment they exist. Proven by
    # spending one call and reading it back.
    from auth.signin import owner_for_auth_user
    from budget.ledger import charge, remaining
    from db.connection import get_conn

    sub = str(uuid.uuid4())
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner, _ = owner_for_auth_user(
                    cur, sub, email="budget-probe@example.invalid", env=OPEN)
                before = remaining(cur, "adzuna", owner)
                verdict = charge(cur, "adzuna", owner)
                after = remaining(cur, "adzuna", owner)

            assert verdict.allowed is True, \
                f"a new owner's first metered call was refused: {verdict}"
            assert before["owner"]["spent"] == 0
            assert after["owner"]["spent"] == 1
            assert after["owner"]["cap"] > 0, "the new owner has no cap at all"
        finally:
            conn.rollback()


@db_tests
def test_the_auth_user_column_is_unique_and_optional():
    # Unique because it is an identity; nullable because the founder and every
    # friend-tier profile has no Supabase auth user and never will.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select is_nullable, data_type from information_schema.columns "
                "where table_schema='public' and table_name='profiles' "
                "  and column_name='auth_user_id'")
            column = cur.fetchone()
            assert column is not None, "profiles.auth_user_id does not exist"
            assert column["is_nullable"] == "YES"

            cur.execute(
                "select count(*) as n from pg_indexes "
                "where schemaname='public' and tablename='profiles' "
                "  and indexdef ilike '%unique%' "
                "  and indexdef ilike '%auth_user_id%'")
            assert cur.fetchone()["n"] == 1, \
                "auth_user_id is not unique — two profiles could claim one identity"
        conn.rollback()
