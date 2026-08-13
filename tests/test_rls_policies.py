"""Row-level security, proven by being refused (Phase 9 task 2a).

The measured starting point, and the reason this file is shaped the way it is:
**every door in this codebase — the engine, the MCP server, the dashboard and
the status page — connects through the same `get_conn()` as `postgres`, and
`postgres` carries `rolbypassrls`.** RLS was therefore switched on across 28
tables and enforcing nothing at all, and policies alone would not have changed
that. `FORCE ROW LEVEL SECURITY` would not have either: FORCE removes the
table-OWNER exemption, not the role attribute.

So the policies are written against a role that cannot bypass them,
`goal_a_app`, and every test here proves refusal **as that role** — assumed
with `SET LOCAL ROLE`, which is enough to drop the bypass because RLS is
evaluated against `current_user`. Task 2b cuts the engine over to it; until
then these policies protect nothing in production, and saying so is part of
the test's job.

This file refuses to assert on policy text. A policy that exists and a policy
that refuses are different claims, and only the second one is worth anything.

How the proofs are shaped, and why:
  * The read refusals run against the founder's REAL rows and write nothing.
  * The write refusals and the derived-table proofs need a SECOND real owner,
    so they insert one into the real tables inside a transaction that always
    rolls back. They must run against the DEPLOYED policies rather than copies
    in a scratch schema — copies would prove the SQL in this repo correct and
    say nothing about what is actually installed.
  * A second owner is not optional. With one owner in the database, "a
    stranger sees zero rows" and "the policies isolate" are indistinguishable
    claims — and specifically, a derived policy whose EXISTS lost its
    correlation (`WHERE c.owner_id = app_owner()` with no
    `c.company_id = role_listings.company_id`) would let every owner read
    every listing while all the stranger-based tests still passed. That is the
    single likeliest regression in the code this file guards, so it is tested
    directly.

Every refusal is paired with the same query succeeding for the owner who owns
the rows. Without that pairing, a missing GRANT, an empty table or a typo in a
name all read as "isolation works" (B-GAE-011, and B-GAE-004 before it).
"""
from __future__ import annotations

import os
import uuid

import pytest

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

APP_ROLE = "goal_a_app"

# A well-formed owner id that belongs to nobody. Never inserted anywhere.
STRANGER = uuid.UUID("dddddddd-dddd-4ddd-addd-dddddddddddd")

# Tables carrying owner_id directly. access_keys is deliberately absent: the
# door has to resolve a presented key to an owner BEFORE it knows who the
# owner is, so it cannot be read under a policy keyed on that same owner.
# That bootstrap is task 2b's problem and is named in the migration.
OWNER_SCOPED = ("my_skills", "my_constraints", "target_companies",
                "target_roles", "cv_blocks", "promotion_rules")

# No owner column of their own; they reach one through target_companies —
# the same seam task 1b proved in the application layer.
DERIVED = ("role_listings", "listing_events", "role_skills")


def _local_owner(cur):
    """The founder's own profile id, read at run time.

    Never hardcoded: it is personal data, this file ships in the public
    snapshot, and a literal would rot the moment the row changed.
    """
    cur.execute("select profile_id from profiles order by created_at limit 1")
    return cur.fetchone()["profile_id"]


def _as_app_role(cur, owner_id):
    """Assume the app role with `owner_id` as the caller, inside this tx."""
    cur.execute("reset role")
    cur.execute(f"set local role {APP_ROLE}")
    cur.execute("select set_config('app.owner_id', %s, true)", (str(owner_id),))


def _count(cur, table):
    cur.execute(f"select count(*) as n from {table}")
    return cur.fetchone()["n"]


@DB_ONLY
def test_the_app_role_exists_and_is_incapable_of_bypassing_rls():
    # The single property everything else in this file rests on. If the role
    # ever gains BYPASSRLS or ends up owning a table, every refusal below
    # turns into a pass that means nothing — and it would do so silently.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select rolbypassrls, rolsuper, rolcanlogin "
                        "from pg_roles where rolname = %s", (APP_ROLE,))
            role = cur.fetchone()
            assert role is not None, f"{APP_ROLE} does not exist"
            assert role["rolbypassrls"] is False, "the app role can bypass RLS"
            assert role["rolsuper"] is False

            cur.execute(
                "select count(*) as n from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "join pg_roles r on r.oid = c.relowner "
                "where n.nspname = 'public' and r.rolname = %s", (APP_ROLE,))
            assert cur.fetchone()["n"] == 0, \
                "the app role owns a table, which exempts it from that table"
        conn.rollback()


@DB_ONLY
def test_a_stranger_is_refused_every_owner_scoped_table_of_real_data():
    # Refusal against the founder's actual rows, proven by attempting to read
    # them. Nothing is written at any point.
    from db.connection import get_conn

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner = _local_owner(cur)

                _as_app_role(cur, STRANGER)
                stranger_sees = {t: _count(cur, t) for t in OWNER_SCOPED}

                _as_app_role(cur, owner)
                owner_sees = {t: _count(cur, t) for t in OWNER_SCOPED}

                cur.execute("reset role")

            assert set(stranger_sees.values()) == {0}, \
                f"a stranger read real rows: {stranger_sees}"
            # the pairing: at least one of these tables must actually hold
            # rows, or "the stranger saw nothing" is a statement about an
            # empty database rather than about a policy
            assert sum(owner_sees.values()) > 0, \
                f"no owner-scoped table holds any rows: {owner_sees}"
        finally:
            conn.rollback()


@DB_ONLY
def test_a_stranger_is_refused_the_tables_that_reach_an_owner_by_join():
    # role_listings, listing_events and role_skills carry no owner column;
    # their policies walk to target_companies. This is the half of the schema
    # where "it has no owner_id" was the reason it went unprotected.
    from db.connection import get_conn

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner = _local_owner(cur)

                _as_app_role(cur, STRANGER)
                stranger_sees = {t: _count(cur, t) for t in DERIVED}

                _as_app_role(cur, owner)
                owner_sees = {t: _count(cur, t) for t in DERIVED}

                cur.execute("reset role")

            assert set(stranger_sees.values()) == {0}, \
                f"a stranger read real listings: {stranger_sees}"
            assert sum(owner_sees.values()) > 0, \
                f"no derived table holds any rows: {owner_sees}"
        finally:
            conn.rollback()


@DB_ONLY
def test_an_unset_owner_sees_nothing_rather_than_everything():
    # Fail-closed. current_setting(..., true) returns NULL when the request
    # forgot to say who it is for, and a NULL comparison is not true — so the
    # answer is zero rows, not the whole table. The opposite default is the
    # kind that ships quietly and is discovered by a user.
    from db.connection import get_conn

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner = _local_owner(cur)

                cur.execute("reset role")
                cur.execute(f"set local role {APP_ROLE}")
                # deliberately NOT setting app.owner_id
                blind = {t: _count(cur, t) for t in OWNER_SCOPED + DERIVED}

                _as_app_role(cur, owner)
                sighted = sum(_count(cur, t) for t in OWNER_SCOPED + DERIVED)
                cur.execute("reset role")

            assert set(blind.values()) == {0}, \
                f"an owner-less request read rows: {blind}"
            assert sighted > 0
        finally:
            conn.rollback()


@DB_ONLY
def test_world_data_stays_readable_because_it_is_not_anybodys():
    # The other half of getting this right. RLS on with no policy denies
    # everything, so the census, the register and the shared ledgers would
    # vanish for the app role at cutover and the nightly run would quietly do
    # nothing. Measured as a real count, not as a policy count.
    from db.connection import get_conn

    world = ("licensed_sponsors", "sponsor_census", "skilled_worker_occupations",
             "soc_going_rates", "sic_codes", "aggregator_ads", "skill_synonyms",
             "review_items", "pipeline_runs")
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                _as_app_role(cur, STRANGER)
                seen = {t: _count(cur, t) for t in world}
                cur.execute("reset role")
            empty = [t for t, n in seen.items() if n == 0]
            assert empty == [], f"world data is invisible to the app role: {empty}"
        finally:
            conn.rollback()


# The only table the app role may delete from, and the reason it may.
# role_skills is DERIVED: accept_reading replaces the whole set per role_id on
# every read, so it is not a keep-all table and never was (0057, B-GAE-023).
# This is a deliberate narrowing of "no DELETE, ever" to the tables that hold
# facts — widening it again is a decision, which is why the list is pinned here
# rather than the assertion being relaxed to "not many deletes".
DELETABLE = {"role_skills"}


@DB_ONLY
def test_the_app_role_can_delete_from_exactly_one_derived_table():
    # Keep-all tables never lose rows; removals are stamps. That rule has
    # lived in prose since Phase 1 — this makes the database hold it, for
    # every table except the one the founder deliberately exempted.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select privilege_type, count(*) as n "
                "from information_schema.role_table_grants "
                "where table_schema = 'public' and grantee = %s "
                "group by privilege_type", (APP_ROLE,))
            held = {r["privilege_type"]: r["n"] for r in cur.fetchall()}
            cur.execute(
                "select table_name from information_schema.role_table_grants "
                "where table_schema = 'public' and grantee = %s "
                "and privilege_type = 'DELETE'", (APP_ROLE,))
            deletable = {r["table_name"] for r in cur.fetchall()}
            # The control. Asserting only "no DELETE" would pass for a role
            # that does not exist, or one with no grants at all — true, and
            # about nothing. So SELECT must actually be held, widely.
            assert held.get("SELECT", 0) >= len(OWNER_SCOPED) + len(DERIVED), \
                f"the app role cannot read enough to be the app role: {held}"
            assert held.get("INSERT", 0) > 0 and held.get("UPDATE", 0) > 0
            assert deletable == DELETABLE, (
                f"the app role's DELETE grants are {sorted(deletable)}, not "
                f"{sorted(DELETABLE)} — a keep-all table can now lose rows, or "
                "the one derived exemption was revoked")
        conn.rollback()


# --- a SECOND real owner: the only shape that proves correlation ----------

OWNER_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-abbb-bbbbbbbbbbbb")


def _seed_owner_b(cur):
    """Give owner B a profile, a company and a listing in the REAL tables.

    Inside a transaction the caller always rolls back. It has to be the real
    tables: copies in a scratch schema would carry copies of the policies and
    prove this repo's SQL correct while saying nothing about what is deployed.
    """
    cur.execute("insert into profiles (profile_id, name) values (%s, 'RLS probe B')",
                (OWNER_B,))
    cur.execute(
        "insert into target_companies (company_name, owner_id, fit_rank, "
        "sponsor_confidence) values ('RLS Probe Ltd', %s, 'High', 'sponsors') "
        "returning company_id", (OWNER_B,))
    company_id = cur.fetchone()["company_id"]
    cur.execute(
        "insert into role_listings (company_id, role_title, location, "
        "role_status, role_url) values (%s, 'RLS Probe Role', 'London, UK', "
        "'open', 'https://example.invalid/rls-probe') returning role_id",
        (company_id,))
    return company_id, cur.fetchone()["role_id"]


@DB_ONLY
def test_two_real_owners_each_see_their_own_listings_and_not_the_others():
    # The correlation proof. A derived policy that dropped its correlation —
    # EXISTS (select 1 from target_companies c where c.owner_id = app_owner())
    # with no c.company_id = role_listings.company_id — passes every
    # stranger-based test in this file and leaks every listing to every owner.
    # Only a second owner holding real rows can tell the difference.
    from db.connection import get_conn

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner_a = _local_owner(cur)
                b_company, b_role = _seed_owner_b(cur)

                _as_app_role(cur, OWNER_B)
                cur.execute("select company_id from target_companies")
                b_companies = {r["company_id"] for r in cur.fetchall()}
                cur.execute("select role_id from role_listings")
                b_listings = {r["role_id"] for r in cur.fetchall()}

                _as_app_role(cur, owner_a)
                cur.execute("select count(*) as n from role_listings")
                a_listing_count = cur.fetchone()["n"]
                cur.execute("select count(*) as n from role_listings "
                            "where role_id = %s", (b_role,))
                a_sees_bs_listing = cur.fetchone()["n"]

                cur.execute("reset role")

            # B sees exactly its own, and nothing of A's
            assert b_companies == {b_company}, \
                f"owner B saw companies that are not its own: {b_companies}"
            assert b_listings == {b_role}, \
                f"owner B saw listings that are not its own: {b_listings}"
            # …and A, who has thousands, sees none of B's
            assert a_listing_count > 1, \
                "owner A has no listings, so this proves nothing"
            assert a_sees_bs_listing == 0, "owner A read owner B's listing"
        finally:
            conn.rollback()


@DB_ONLY
def test_a_row_stamped_with_someone_elses_owner_is_refused_on_write():
    # WITH CHECK, proven by attempting the write. Without this the entire
    # write half of the policy set ships unexercised — a caller could stamp
    # rows into another owner's account even while reads were airtight.
    import psycopg

    from db.connection import get_conn

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner_a = _local_owner(cur)
                _seed_owner_b(cur)
                _as_app_role(cur, OWNER_B)

                # 1 · a direct insert stamped with A's owner_id
                cur.execute("savepoint w1")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(
                        "insert into my_skills (skill, owner_id) "
                        "values ('Stolen Skill', %s)", (owner_a,))
                cur.execute("rollback to savepoint w1")

                # 2 · the control: the same insert as ITSELF must succeed, or
                #     the refusal above would only mean "writes are broken"
                cur.execute("savepoint w2")
                cur.execute("insert into my_skills (skill, owner_id) "
                            "values ('Own Skill', %s)", (OWNER_B,))
                cur.execute("rollback to savepoint w2")

                # 3 · an update that moves one of B's own rows to A
                cur.execute("savepoint w3")
                cur.execute("insert into my_skills (skill, owner_id) "
                            "values ('Movable', %s) returning id", (OWNER_B,))
                skill_id = cur.fetchone()["id"]
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute("update my_skills set owner_id = %s "
                                "where id = %s", (owner_a, skill_id))
                cur.execute("rollback to savepoint w3")

                # 4 · the derived table: a listing hung off A's company.
                #     WITH CHECK walks to target_companies, so this is the
                #     insert that would smuggle a row into A's queue.
                cur.execute("savepoint w4")
                cur.execute("reset role")
                cur.execute("select company_id from target_companies "
                            "where owner_id = %s limit 1", (owner_a,))
                a_company = cur.fetchone()["company_id"]
                _as_app_role(cur, OWNER_B)
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(
                        "insert into role_listings (company_id, role_title, "
                        "location, role_status, role_url) values "
                        "(%s, 'Smuggled', 'London, UK', 'open', "
                        "'https://example.invalid/smuggled')", (a_company,))
                cur.execute("rollback to savepoint w4")

                cur.execute("reset role")
        finally:
            conn.rollback()
