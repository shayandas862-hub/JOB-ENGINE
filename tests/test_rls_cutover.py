"""Task 2b: the MCP door runs as `goal_a_app`, so the DATABASE does the refusing.

`tests/test_rls_policies.py` proved the policies refuse when a connection
assumes the app role. This file proves the thing that actually protects
anybody: that a **real tool call, over the real MCP client, on a real
connection** assumes that role — and is refused.

Two design choices here are the whole point, and both are deliberate.

**The application-layer owner filter is REMOVED.** `fetch_queue` carries
`where owner_id = %s` (task 1b). With it in place owner B reads nothing
whether or not RLS is live, so a passing test would say nothing at all about
the cutover — it would restate task 1b and wear a security badge. These tests
swap in a query with **no owner predicate**, so anything that comes back came
back because the database allowed it.

**Every refusal is paired with the same call succeeding for the owner who owns
the rows.** An empty result has many uninteresting causes — an empty fixture, a
missing GRANT, a typo in a view name. Only "A sees rows here and B sees none"
separates isolation from breakage.

The connection is shared with the tool by patching `session.get_conn`, not
`read_tools.get_conn`: patching the tool's own name would skip `scoped_conn`
entirely and pass without ever exercising the role switch, which is precisely
the trap this file exists to avoid. What is patched is only where the
connection comes FROM; the role switch, the owner resolution and the tool body
are all the real ones, and the whole thing rolls back.

Opt-in (`RUN_DB_TESTS=1`): it needs the real database, and no fake can stand in
— a fake cursor has no roles and no policies.
"""
from __future__ import annotations

import asyncio
import contextlib
import os

import pytest
from fastmcp import Client

from tests.test_rls_policies import (APP_ROLE, OWNER_B, _local_owner,
                                     _seed_owner_b)

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")


class _Token:
    """The shape `mcp_server.identity.current_owner` reads off a verified key."""

    def __init__(self, owner: str):
        self.client_id = owner


def _unfiltered_queue(cur, owner_id, limit: int = 20) -> list[dict]:
    """`fetch_queue` with its `where owner_id = %s` DELETED, on purpose.

    owner_id is accepted and ignored so the signature still matches the tool's
    call. If this ever quietly regains a filter, these tests go green for the
    wrong reason — that is why the absence is stated here rather than implied.
    """
    cur.execute("select role_id, owner_id::text as owner_id "
                "from v_apply_queue limit %s", (limit,))
    return cur.fetchall()


def _call_queue_as(monkeypatch, mcp, owner) -> list[dict]:
    """Drive the real get_apply_queue tool as `owner`, through a real Client."""
    from mcp_server import identity
    monkeypatch.setattr(identity, "get_access_token", lambda: _Token(str(owner)))

    async def go():
        async with Client(mcp) as client:
            return await client.call_tool("get_apply_queue", {})

    return asyncio.run(go()).structured_content["result"]


@DB_ONLY
def test_a_real_tool_is_refused_another_owners_rows_by_the_database(monkeypatch):
    # The cutover's done-looks-like. Before `scoped_conn` assumed the app role
    # this failed exactly as it should: owner B, on the unfiltered path, read
    # owner A's queue in full, because `postgres` carries rolbypassrls and the
    # policies written in task 2a were refusing nobody in production.
    from db.connection import get_conn
    from mcp_server import read_tools, session
    from mcp_server.server import build_server

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                owner_a = _local_owner(cur)
                _seed_owner_b(cur)

            @contextlib.contextmanager
            def _shared():
                # Never commits and never closes: the tool has to run inside
                # THIS transaction or it would not see owner B, who only
                # exists until the rollback below.
                yield conn

            monkeypatch.setattr(session, "get_conn", _shared)
            monkeypatch.setattr(read_tools, "fetch_queue", _unfiltered_queue)
            mcp = build_server([read_tools.register])

            b_rows = _call_queue_as(monkeypatch, mcp, OWNER_B)
            # SET LOCAL is transaction-scoped, and this transaction is shared
            # rather than per-call as it is in production — so the role has to
            # be dropped by hand between callers.
            with conn.cursor() as cur:
                cur.execute("reset role")
            a_rows = _call_queue_as(monkeypatch, mcp, owner_a)
            with conn.cursor() as cur:
                cur.execute("reset role")

            assert a_rows, (
                "owner A read nothing on the unfiltered path — the view, the "
                "GRANT or the fixture is broken, so B's empty result below "
                "would prove nothing")
            assert b_rows == [], (
                f"owner B read {len(b_rows)} of owner A's queue rows through a "
                "real tool: the door is not running as the app role")
            assert all(r["owner_id"] == str(owner_a) for r in a_rows), \
                "the unfiltered path returned rows belonging to somebody else"
        finally:
            conn.rollback()


@DB_ONLY
def test_the_app_role_holds_every_privilege_the_engine_actually_uses():
    # B-GAE-023's class guard, and the one that would have caught it before the
    # cutover rather than during it. The suite was fully green while
    # submit_reading was dead in production, because a fake cursor enforces no
    # privilege and no test drives a write tool against a real table.
    #
    # So the privileges are checked against the SQL the engine really writes:
    # every table/verb pair found in src/ must be a thing goal_a_app may do.
    # Statements naming something that is not a real table (dynamic SQL, a
    # scratch name) are skipped rather than guessed at.
    import pathlib
    import re

    from db.connection import get_conn

    root = pathlib.Path(__file__).resolve().parents[1]
    patterns = ((re.compile(r"\bdelete\s+from\s+([a-z_][a-z0-9_]*)", re.I), "DELETE"),
                (re.compile(r"\binsert\s+into\s+([a-z_][a-z0-9_]*)", re.I), "INSERT"),
                (re.compile(r"\bupdate\s+([a-z_][a-z0-9_]*)\s+set\b", re.I), "UPDATE"))

    # The one module the scan must NOT read, and the reason is the whole point
    # of task 5: `budget.ledger` writes the spend counters on the meter's OWN
    # connection (budget.gate opens it with the engine's DATABASE_URL), never
    # on the door's scoped one. Migration 0060 then revokes those writes from
    # goal_a_app on purpose — a key holder who could write the ledger could
    # zero their own spend, and the cap would be decoration. So these three
    # pairs are exactly the case this test is looking for, inverted: SQL the
    # door cannot run, which no door ever runs.
    #
    # An exemption, not a loosening. If a TOOL ever writes a budget row
    # through `scoped_conn`, it will be dead in production and this list is
    # the reason nothing caught it — so the file stays a single named module,
    # and adding a second one is a decision, not an edit.
    ENGINE_ONLY_WRITERS = {"budget/ledger.py"}

    wanted = set()
    for path in (root / "src").rglob("*.py"):
        if any(str(path).endswith(name) for name in ENGINE_ONLY_WRITERS):
            continue
        text = path.read_text()
        for pattern, verb in patterns:
            for table in pattern.findall(text):
                wanted.add((table.lower(), verb))

    missing = []
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                for table, verb in sorted(wanted):
                    cur.execute("select to_regclass(%s) is not null as real",
                                (f"public.{table}",))
                    if not cur.fetchone()["real"]:
                        continue
                    cur.execute(
                        "select has_table_privilege(%s, %s, %s) as allowed",
                        (APP_ROLE, f"public.{table}", verb))
                    if not cur.fetchone()["allowed"]:
                        missing.append(f"{verb} on {table}")
        finally:
            conn.rollback()

    assert len(wanted) > 20, \
        f"the scan found almost nothing ({len(wanted)} pairs) — it is broken"
    assert missing == [], (
        f"the engine issues SQL the MCP door's role cannot run: {missing}. "
        "Every one of these is a tool that is green in the suite and dead in "
        "production.")


@DB_ONLY
def test_the_reading_tray_can_replace_its_derived_skill_rows(monkeypatch):
    # The specific half of B-GAE-023: submit_reading -> accept_reading runs
    # `delete from role_skills`, which the app role could not do at all. The
    # founder's call (2026-08-11) was to grant DELETE on this one derived
    # table rather than weaken the rule everywhere or restructure the engine
    # for a security refactor — role_skills is rebuilt from the JD on every
    # read, which is why it is not a keep-all table.
    from db.connection import get_conn

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "select l.role_id from role_listings l "
                    "join target_companies c on c.company_id = l.company_id "
                    "join role_skills s on s.role_id = l.role_id "
                    "where c.owner_id = (select profile_id from profiles "
                    "                    order by created_at limit 1) limit 1")
                row = cur.fetchone()
                if row is None:
                    pytest.skip("no read listing with skills to replace")
                owner = _local_owner(cur)

                cur.execute("reset role")
                cur.execute(f"set local role {APP_ROLE}")
                cur.execute("select set_config('app.owner_id', %s, true)",
                            (str(owner),))
                # the exact statement src/reading/accept.py issues
                cur.execute("delete from role_skills where role_id = %s",
                            (row["role_id"],))
                deleted = cur.rowcount
                cur.execute("reset role")

            assert deleted > 0, \
                "the replace deleted nothing, so it proves no privilege"
        finally:
            conn.rollback()


@DB_ONLY
def test_the_door_assumes_the_app_role_rather_than_merely_setting_the_owner(
        monkeypatch):
    # Setting app.owner_id without dropping to goal_a_app would leave every
    # query running as postgres, which bypasses RLS — and every scoping test
    # in the suite would still pass, because the application filter would be
    # doing the work. So the role itself is asserted, from inside the
    # transaction the tool body runs in.
    from db.connection import get_conn
    from mcp_server import session

    seen = {}
    with get_conn() as conn:
        try:
            @contextlib.contextmanager
            def _shared():
                yield conn

            monkeypatch.setattr(session, "get_conn", _shared)
            from mcp_server import identity
            monkeypatch.setattr(identity, "get_access_token",
                                lambda: _Token(str(OWNER_B)))

            with session.scoped_conn() as scoped:
                with scoped.cursor() as cur:
                    cur.execute("select current_user, "
                                "public.app_owner()::text as owner")
                    seen = cur.fetchone()
            with conn.cursor() as cur:
                cur.execute("reset role")

            assert seen["current_user"] == "goal_a_app", (
                f"the tool body ran as {seen['current_user']!r}, which bypasses "
                "RLS — the policies protect nothing on this connection")
            assert seen["owner"] == str(OWNER_B), \
                "app.owner_id did not carry the verified caller into the tx"
        finally:
            conn.rollback()
