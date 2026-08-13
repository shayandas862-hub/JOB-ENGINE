"""Owner scoping, proven by being refused (Phase 9 task 1b).

Task 1a answered *who is calling*. It did not scope the reads that never took
an owner, so a friend's key would have opened the founder's queue. This is the
test that says the hole is shut — and it says it the only way that counts, by
seeding two real owners and ATTEMPTING to read across, rather than by reading
SQL text and agreeing with it.

The fixture is deliberately not hand-written. Tables are structural copies of
production's (``create table … like public.X including all``) and the three
views are created from **production's own definitions**, read back with
``pg_get_viewdef``. So what is under test is the real view logic against the
real column shapes; only the rows are invented, and they live in a scratch
schema that is dropped at the end. The founder's data is never read or written.

Every refusal is paired with owner A making the SAME call successfully. That
pairing is the whole design: an empty fixture, a typo in a name, a schema that
failed to build — each of those would make "B sees nothing" true for reasons
that have nothing to do with security. B-GAE-004 is this codebase's most
persistent defect and a one-sided isolation test is exactly its shape.
"""
from __future__ import annotations

import os
import uuid

import pytest

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

SCHEMA = "owner_scoping_test"

OWNER_A = uuid.UUID("11111111-1111-4111-a111-111111111111")
OWNER_B = uuid.UUID("22222222-2222-4222-a222-222222222222")

CHANNEL_A = "ntfy:owner-a-private-topic"
CHANNEL_B = "ntfy:owner-b-private-topic"

# Enough of the schema to build the three views and exercise every scoped
# function. Order matters only for readability — LIKE copies no foreign keys.
TABLES = ("profiles", "target_companies", "role_listings", "listing_events",
          "role_skills", "my_skills", "skill_synonyms", "my_constraints",
          "target_roles", "soc_going_rates")

# v_skill_gap reads v_skill_demand reads v_apply_queue: create in that order.
VIEWS = ("v_apply_queue", "v_skill_demand", "v_skill_gap")


def _build_scratch_schema(cur):
    """A private copy of the real shapes, with the real view definitions."""
    cur.execute(f"drop schema if exists {SCHEMA} cascade")
    cur.execute(f"create schema {SCHEMA}")

    # Read the definitions while search_path is still public. pg_get_viewdef
    # qualifies any name that is not reachable unqualified under the CURRENT
    # search_path — so reading these AFTER switching to the scratch schema
    # returns "public.role_listings", and the copied views then read
    # production's tables. The symptom is an empty scratch queue, which looks
    # like a fixture that failed to seed rather than a view pointed at the
    # wrong database. Hence the assertion, not just the ordering.
    definitions = {}
    for view in VIEWS:
        cur.execute("select pg_get_viewdef(%s::regclass, true) as def",
                    (f"public.{view}",))
        definitions[view] = cur.fetchone()["def"]
        assert "public." not in definitions[view], (
            f"{view}'s definition came back schema-qualified, so the copy "
            "would read production's tables instead of the scratch ones")

    cur.execute(f"set search_path to {SCHEMA}")
    for table in TABLES:
        cur.execute(f"create table {table} (like public.{table} including all)")
    for view in VIEWS:
        # Unqualified names now resolve against the scratch schema, so the
        # copied view reads the copied tables. security_invoker is re-asserted
        # rather than assumed (B-GAE-006: reloptions do not travel with a
        # definition).
        cur.execute(f"create view {view} with (security_invoker = true) "
                    f"as {definitions[view]}")


def _seed_two_owners(cur):
    """One company, one open listing, one skill and one event per owner.

    Both listings carry the SAME title and UK location, and both owners' search
    titles admit that title, so the queue view would return either listing to
    either owner if scoping were the only thing stopping it. Were the rows
    different, "B cannot see A's listing" could just mean B's search never
    matched it — a green test proving nothing.

    The two search titles are worded differently for a reason that has since
    gone away: ``target_roles`` used to be UNIQUE on search_title alone, so two
    owners could not literally store the same target role (B-GAE-010).
    Migration 0055 replaced that key with ``UNIQUE (owner_id, search_title)``,
    so the differing wording is now historical rather than required. It is kept
    because both titles still match 'AI Engineer' through the view's substring
    gate, which is what the property above needs.
    """
    cur.execute(
        "insert into profiles (profile_id, name, notification_channel) "
        "values (%s, 'Owner A', %s), (%s, 'Owner B', %s)",
        (OWNER_A, CHANNEL_A, OWNER_B, CHANNEL_B))
    cur.execute(
        "insert into target_roles (search_title, canonical_role, owner_id) "
        "values ('AI Engineer', 'AI Engineer', %s), "
        "('Engineer', 'AI Engineer', %s)",
        (OWNER_A, OWNER_B))

    listings = {}
    for owner, company in ((OWNER_A, "A Corp"), (OWNER_B, "B Corp")):
        cur.execute(
            "insert into target_companies (company_name, owner_id, fit_rank, "
            "sponsor_confidence, lane) values (%s, %s, 'High', "
            "'sponsors', 'core') returning company_id",
            (company, owner))
        company_id = cur.fetchone()["company_id"]
        cur.execute(
            "insert into role_listings (company_id, role_title, location, "
            "role_status, sponsors_this_role, role_url, jd_full) "
            "values (%s, 'AI Engineer', 'London, UK', 'open', 'sponsors', "
            "%s, 'jd') returning role_id",
            (company_id, f"https://x/{company}"))
        role_id = cur.fetchone()["role_id"]
        listings[owner] = role_id

        cur.execute(
            "insert into listing_events (role_id, event_type) "
            "values (%s, 'appeared')", (role_id,))
        cur.execute(
            "insert into role_skills (role_id, skill_asked, skill_norm, "
            "skill_type) values (%s, %s, %s, 'must')",
            (role_id, f"Skill Of {company}", f"skill of {company.lower()}"))

    # Owner A holds the skill A's listing asks for. Owner B holds nothing, so
    # a leak shows up twice over: as A's demand and as A's my_level.
    # my_skills.skill_norm is GENERATED (lower/collapse of skill) — insert raw
    # facts only, exactly as the licensed_sponsors rule in CLAUDE.md says.
    cur.execute(
        "insert into my_skills (skill, level, status, owner_id) "
        "values ('Skill Of A Corp', 'strong', 'active', %s)",
        (OWNER_A,))
    return listings


@DB_ONLY
def test_owner_b_is_refused_every_one_of_owner_as_rows():
    from analysis.job_gap import fetch_job_gap
    from applyqueue import (fetch_job, fetch_queue, fetch_skill_gaps,
                            mark_applied, snooze_listing)
    from db.connection import get_conn
    from history.events import history_for_role
    from notify.nudges import load_channel

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                _build_scratch_schema(cur)
                listings = _seed_two_owners(cur)
                a_role, b_role = listings[OWNER_A], listings[OWNER_B]

                # --- the queue -------------------------------------------
                a_queue = [r["role_id"] for r in fetch_queue(cur, OWNER_A)]
                b_queue = [r["role_id"] for r in fetch_queue(cur, OWNER_B)]
                assert a_queue == [a_role], "the fixture never built A's queue"
                assert b_queue == [b_role]
                assert a_role not in b_queue

                # --- one listing -----------------------------------------
                assert fetch_job(cur, OWNER_A, a_role) is not None
                assert fetch_job(cur, OWNER_B, a_role) is None

                # --- that listing's gap ----------------------------------
                a_gap = fetch_job_gap(cur, OWNER_A, a_role)
                assert a_gap is not None and a_gap["have_count"] == 1
                assert fetch_job_gap(cur, OWNER_B, a_role) is None
                # B asking about B's own listing must not find A's skill
                b_gap = fetch_job_gap(cur, OWNER_B, b_role)
                assert b_gap["have_count"] == 0 and b_gap["missing_count"] == 1

                # --- that listing's history ------------------------------
                assert len(history_for_role(cur, OWNER_A, a_role)) == 1
                assert history_for_role(cur, OWNER_B, a_role) == []

                # --- the aggregate skill gap -----------------------------
                a_gaps = {r["skill"] for r in fetch_skill_gaps(cur, OWNER_A)}
                b_gaps = {r["skill"] for r in fetch_skill_gaps(cur, OWNER_B)}
                assert a_gaps == set(), "A holds the only skill A's role asks"
                assert b_gaps == {"Skill Of B Corp"}
                assert "Skill Of A Corp" not in b_gaps

                # --- the writes ------------------------------------------
                assert mark_applied(cur, OWNER_B, a_role) is None
                assert snooze_listing(cur, OWNER_B, a_role) is None
                cur.execute("select application_status, applied_date, "
                            "nudged_at from role_listings where role_id = %s",
                            (a_role,))
                untouched = cur.fetchone()
                assert untouched["application_status"] == "not_applied"
                assert untouched["applied_date"] is None
                assert untouched["nudged_at"] is None
                # …and the same calls DO work for the owner who owns the row
                assert mark_applied(cur, OWNER_A, a_role) == "AI Engineer"
                assert snooze_listing(cur, OWNER_A, a_role) == "AI Engineer"

                # --- the one that leaves the building --------------------
                assert load_channel(cur, OWNER_A) == CHANNEL_A
                assert load_channel(cur, OWNER_B) == CHANNEL_B
        finally:
            # Rollback FIRST. A failed assertion can leave the transaction
            # aborted, and a DROP issued into an aborted transaction raises
            # InFailedSqlTransaction — which then replaces the real failure in
            # the report. The rollback undoes the scratch schema too (it was
            # created in this transaction); the drop after it is belt and
            # braces for any connection that turns out to be autocommit.
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {SCHEMA} cascade")
            conn.rollback()


@DB_ONLY
def test_role_listings_reaches_an_owner_only_through_its_company():
    # The seam task 1 was told to prove hard or replace with a column. It is
    # proven, so it must stay proven: if role_listings ever gains an owner_id,
    # there are then TWO answers to "whose listing is this" and they can
    # disagree. This fails the day someone adds one, which is the point.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select column_name from information_schema.columns "
                "where table_schema = 'public' and table_name = %s "
                "and column_name = 'owner_id'", ("role_listings",))
            assert cur.fetchone() is None, \
                "role_listings gained an owner_id — the scoping seam now has " \
                "two sources of truth; pick one deliberately"

            # and the route it does have is real, on both sides
            cur.execute(
                "select table_name, column_name from information_schema.columns "
                "where table_schema = 'public' "
                "and (table_name, column_name) in "
                "(('role_listings','company_id'), ('target_companies','owner_id'), "
                "('v_apply_queue','owner_id'), ('v_skill_gap','owner_id'))")
            found = {(r["table_name"], r["column_name"]) for r in cur.fetchall()}
            assert found == {("role_listings", "company_id"),
                             ("target_companies", "owner_id"),
                             ("v_apply_queue", "owner_id"),
                             ("v_skill_gap", "owner_id")}
        conn.rollback()


# --- the single-user DEFAULTs, dropped (Phase 9 task 2a) -------------------

# The smallest legal row per table, as (columns, values), with owner_id left
# out — every other NOT NULL column filled, so the violation that comes back
# can only be owner_id's. Written out rather than generated: an insert that
# tripped over `kind` first would report a pass for the wrong column, which is
# how a probe like this quietly stops probing.
MINIMAL_ROW = {
    "cv_blocks": ("kind, fact_text", "'role', 'probe'"),
    "my_constraints": ("kind", "'probe'"),
    "my_skills": ("skill", "'Probe Skill'"),
    "target_companies": ("company_name", "'Probe Ltd'"),
    "target_roles": ("search_title, canonical_role", "'probe', 'probe'"),
}
DEFAULTED = tuple(MINIMAL_ROW)


@DB_ONLY
def test_an_unstamped_insert_fails_loudly_instead_of_becoming_the_founders():
    # Migration 0018 gave five tables `owner_id DEFAULT
    # '00000000-0000-4000-a000-000000000001'`, correct while there was one
    # person and a silent mis-attribution the moment there were two: a write
    # that forgot to say whose it was became HIS. Every insert in src/ was
    # audited and passes owner_id explicitly, so the default protected nothing
    # and only hid mistakes.
    #
    # Proven per table by attempting the ownerless insert, in scratch copies —
    # nothing is written to the real tables.
    import psycopg

    from db.connection import get_conn

    schema = "owner_default_probe"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}")
                for table in DEFAULTED:
                    cur.execute(f"create table {table} "
                                f"(like public.{table} including all)")

                for table, (cols, vals) in MINIMAL_ROW.items():
                    cur.execute("savepoint probe")
                    with pytest.raises(psycopg.errors.NotNullViolation,
                                       match="owner_id"):
                        cur.execute(
                            f"insert into {table} ({cols}) values ({vals})")
                    cur.execute("rollback to savepoint probe")

                    # The control: the SAME row WITH an owner must land, or
                    # "it raised" would only mean the row was malformed and
                    # the probe would pass whatever the default did.
                    cur.execute("savepoint stamped")
                    cur.execute(
                        f"insert into {table} ({cols}, owner_id) "
                        f"values ({vals}, %s)", (OWNER_A,))
                    cur.execute(f"select count(*) as n from {table}")
                    assert cur.fetchone()["n"] == 1, \
                        f"a stamped insert into {table} did not land"
                    cur.execute("rollback to savepoint stamped")
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.rollback()


@DB_ONLY
def test_no_owner_scoped_table_reintroduces_a_default_owner():
    # The standing version of the test above: any FUTURE table that carries
    # owner_id must not carry a default for it either. access_keys was built
    # this way from the start (task 1a); this makes that the rule.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select table_name, column_default "
                "from information_schema.columns "
                "where table_schema = 'public' and column_name = 'owner_id' "
                "and column_default is not null")
            defaulted = {r["table_name"]: r["column_default"]
                         for r in cur.fetchall()}
            assert defaulted == {}, \
                f"owner_id carries a default again: {defaulted}"
        conn.rollback()
