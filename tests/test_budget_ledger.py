"""The spend ledger against the real tables (RUN_DB_TESTS=1) — task 5.

An offline fake cannot say anything true about this module: the whole design
is a conditional upsert whose WHERE clause is the cap, plus RLS policies that
only exist in the database. A FakeCursor would happily "pass" every assertion
below while the real table refused nothing — the writer-coverage ratchet's
exact argument, and the reason `budget.ledger` arrives with this file.

The adversarial half is the point: user B's identical call must still work
while user A is refused, and the world cap must stop both. Proven by running
the calls and reading the refusals, never by reading the policy text.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

DAY = "2026-08-12"


def _cap(cur, source, *, world, owner):
    """Bend this source's caps for the length of the test transaction."""
    cur.execute("update api_budget_caps set world_daily=%s, owner_daily=%s "
                "where source=%s", (world, owner, source))
    assert cur.rowcount == 1, f"no cap row for {source} — the seed is missing"


def _owner(cur, name):
    from criteria.profiles import insert_profile
    from mcp_server.session import adopt_owner
    owner_id = str(uuid4())
    adopt_owner(cur, owner_id)
    insert_profile(cur, owner_id, name)
    return owner_id


# ---- the shape of the thing -------------------------------------------------

def test_the_three_sources_are_seeded_with_caps():
    from budget import ledger
    from db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("select source, world_daily, owner_daily "
                    "from api_budget_caps order by source")
        rows = {r["source"]: r for r in cur.fetchall()}
    assert set(rows) == set(ledger.SOURCES)
    for source, row in rows.items():
        assert row["world_daily"] > 0, f"{source} has a world cap of zero"
        assert row["owner_daily"] > 0, f"{source} has an owner cap of zero"
        assert row["owner_daily"] <= row["world_daily"], (
            f"{source}: one owner may not be allowed more than the world")


def test_the_seeded_world_caps_clear_what_the_nightly_run_already_spends():
    # The cap is a backstop, not a throttle on the founder's own machine.
    # Measured 2026-08-12 from api_quota_ledger: reed peaked at 950 across 11
    # ledgered days, adzuna at 240 across 9. A cap under those would refuse
    # work that already runs every night.
    from db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("select l.source, max(l.calls) as peak, c.world_daily "
                    "from api_quota_ledger l "
                    "join api_budget_caps c on c.source = l.source "
                    "group by l.source, c.world_daily")
        for row in cur.fetchall():
            assert row["world_daily"] >= row["peak"], (
                f"{row['source']}: world cap {row['world_daily']} is below "
                f"the {row['peak']} calls a real day has already needed")


# ---- the founder's night is unchanged --------------------------------------

def test_a_world_run_debits_the_world_and_never_an_owner():
    from budget import ledger
    from db.connection import get_conn
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("delete from api_owner_spend where day=%s", (DAY,))
                before = ledger.remaining(cur, "reed", None, DAY)
                verdict = ledger.charge(cur, "reed", None, DAY)
                after = ledger.remaining(cur, "reed", None, DAY)
                assert verdict.allowed is True
                assert verdict.owner_id is None
                assert verdict.owner_spent is None
                assert after["world"]["spent"] == before["world"]["spent"] + 1
                cur.execute("select count(*) as n from api_owner_spend "
                            "where day=%s", (DAY,))
                assert cur.fetchone()["n"] == 0, (
                    "a world stage wrote an owner budget row — the founder's "
                    "night is no longer byte-identical")
        finally:
            conn.rollback()


# ---- the adversarial two-owner proof ---------------------------------------

def test_one_owner_spends_out_while_the_other_is_untouched():
    from budget import ledger
    from db.connection import get_conn
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                _cap(cur, "adzuna", world=100, owner=2)
                cur.execute("delete from api_quota_ledger where source='adzuna' "
                            "and day=%s", (DAY,))
                a, b = _owner(cur, "Owner A"), _owner(cur, "Owner B")

                assert ledger.charge(cur, "adzuna", a, DAY).allowed
                assert ledger.charge(cur, "adzuna", a, DAY).allowed
                refused = ledger.charge(cur, "adzuna", a, DAY)

                assert refused.allowed is False
                assert refused.refused_by == "owner"
                assert refused.owner_spent == 2 and refused.owner_cap == 2
                assert "resets at midnight UTC" in refused.message
                assert refused.receipts["owner"]["remaining"] == 0

                # B's identical call, at the same second, still works.
                allowed = ledger.charge(cur, "adzuna", b, DAY)
                assert allowed.allowed is True, (
                    "owner A's exhausted budget refused owner B — the budget "
                    "is global, not per-owner")

                # A's refusal cost the world nothing: 2 (A) + 1 (B) = 3.
                cur.execute("select calls from api_quota_ledger "
                            "where source='adzuna' and day=%s", (DAY,))
                assert cur.fetchone()["calls"] == 3, (
                    "a refused owner call still debited the world cap")
        finally:
            conn.rollback()


def test_the_world_cap_stops_every_owner_once_it_empties():
    from budget import ledger
    from db.connection import get_conn
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                # owner_daily may not exceed world_daily (the table's own
                # CHECK — a per-owner budget larger than the shared quota is
                # a promise the provider never made), so both are 2 and the
                # WORLD is what runs out first for the third call.
                _cap(cur, "reed", world=2, owner=2)
                cur.execute("delete from api_quota_ledger where source='reed' "
                            "and day=%s", (DAY,))
                a, b = _owner(cur, "Owner A"), _owner(cur, "Owner B")

                assert ledger.charge(cur, "reed", a, DAY).allowed
                assert ledger.charge(cur, "reed", b, DAY).allowed
                for who in (a, b, None):
                    refused = ledger.charge(cur, "reed", who, DAY)
                    assert refused.allowed is False
                    assert refused.refused_by == "world"
                    assert refused.world_spent == 2

                # The world refusal must not have quietly spent A's budget.
                cur.execute("select calls from api_owner_spend where "
                            "owner_id=%s and source='reed' and day=%s", (a, DAY))
                assert cur.fetchone()["calls"] == 1, (
                    "a world-refused call still debited the owner's budget")
        finally:
            conn.rollback()


def test_an_unknown_source_is_refused_rather_than_spent_freely():
    # Fail closed: a source with no cap row has no budget, not an infinite one.
    from budget import ledger
    from db.connection import get_conn
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                verdict = ledger.charge(cur, "not_a_source", None, DAY)
                assert verdict.allowed is False
        finally:
            conn.rollback()


# ---- the door's own refusals (RLS) -----------------------------------------

def test_an_owner_cannot_read_another_owners_budget_through_the_door():
    from budget import ledger
    from db.connection import get_conn
    from mcp_server.session import adopt_owner
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                a, b = _owner(cur, "Owner A"), _owner(cur, "Owner B")
                ledger.charge(cur, "reed", a, DAY)
                ledger.charge(cur, "reed", b, DAY)

                # The paired control. Without it this test would pass just as
                # happily against two rows that were never written, and would
                # be proving nothing about any policy.
                cur.execute("select owner_id from api_owner_spend "
                            "where day=%s", (DAY,))
                assert {str(r["owner_id"]) for r in cur.fetchall()} == {a, b}

                cur.execute("set local role goal_a_app")
                adopt_owner(cur, a)
                cur.execute("select owner_id from api_owner_spend "
                            "where day=%s", (DAY,))
                seen = {str(r["owner_id"]) for r in cur.fetchall()}
                assert seen == {a}, f"owner A saw other owners' spend: {seen}"
        finally:
            conn.rollback()


def test_the_door_reads_the_world_ledger_and_can_never_write_it():
    import psycopg

    from db.connection import get_conn
    from mcp_server.session import adopt_owner
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner = _owner(cur, "Owner A")
                # Paired control: the engine role writes it fine, so what
                # refuses below is the role, not a broken statement.
                cur.execute("insert into api_quota_ledger (source, day, calls) "
                            "values ('reed', %s, 1) on conflict (source, day) "
                            "do update set calls = api_quota_ledger.calls",
                            (DAY,))
                cur.execute("set local role goal_a_app")
                adopt_owner(cur, owner)

                cur.execute("select 1 from api_quota_ledger limit 1")   # reads
                cur.execute("select 1 from api_budget_caps limit 1")    # reads

                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(
                        "insert into api_quota_ledger (source, day, calls) "
                        "values ('reed', %s, 999999)", (DAY,))
        finally:
            conn.rollback()


def test_an_owner_cannot_forge_their_own_budget_through_the_door():
    # The refusal that matters most: if the door could write api_owner_spend,
    # a key holder could zero their own spend and the cap would be decoration.
    import psycopg

    from budget import ledger
    from db.connection import get_conn
    from mcp_server.session import adopt_owner
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner = _owner(cur, "Owner A")
                ledger.charge(cur, "reed", owner, DAY)
                cur.execute("set local role goal_a_app")
                adopt_owner(cur, owner)
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute("update api_owner_spend set calls = 0 "
                                "where owner_id = %s", (owner,))
        finally:
            conn.rollback()


def test_the_door_reads_its_own_remaining_budget():
    # What sweep_status surfaces, read under the door's own role and policies.
    from budget import ledger
    from db.connection import get_conn
    from mcp_server.session import adopt_owner
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner = _owner(cur, "Owner A")
                ledger.charge(cur, "reed", owner, DAY)
                cur.execute("set local role goal_a_app")
                adopt_owner(cur, owner)
                left = ledger.remaining(cur, "reed", owner, DAY)
                assert left["owner"]["spent"] == 1
                assert left["owner"]["remaining"] == left["owner"]["cap"] - 1
                assert left["world"]["cap"] > 0
        finally:
            conn.rollback()
