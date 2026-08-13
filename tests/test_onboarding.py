"""create_profile — the operator's onboarding door (Phase 9 task 4).

The row every per-owner surface hangs off is created HERE, by conversation,
instead of by an operator SQL ritual. Two rules under test:

* Operator-only until sign-in lands (task 6): the founder's bootstrap token
  (or the local stdio door) may create profiles; a minted friend key is
  refused. A friend can set up their OWN profile's lens, skills and channel
  — they cannot mint new identities.
* The app role's own policy (`profile_id = app_owner()`, WITH CHECK) means
  the insert can only happen AS the new owner — so the tool adopts the new
  id for exactly one statement, through the one sanctioned re-scope helper
  in mcp_server.session. Anything else calling set_config is the
  B-GAE-027 shape at the MCP layer: an identity smuggled past the door.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor

ROOT = Path(__file__).resolve().parents[1]

FRIEND = SimpleNamespace(client_id="friend-1", scopes=["owner"])
FOUNDER = SimpleNamespace(client_id="operator-1", scopes=["owner", "bootstrap"])


def _run(coro):
    return asyncio.run(coro)


def _server(monkeypatch, cur=None, token="unset"):
    from mcp_server import onboarding_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(onboarding_tools, "get_conn",
                        lambda: fake_conn(cur if cur is not None
                                          else FakeCursor()))
    monkeypatch.setattr(onboarding_tools, "_owner", lambda c: "operator-1")
    if token != "unset":
        monkeypatch.setattr(onboarding_tools, "_token", lambda: token)
    return build_server()


def _create(mcp, name="Sam"):
    async def go():
        async with Client(mcp) as client:
            return await client.call_tool("create_profile", {"name": name})
    return _run(go()).data


def test_a_minted_friend_key_cannot_create_profiles(monkeypatch):
    cur = RoutingCursor([])
    data = _create(_server(monkeypatch, cur, token=FRIEND))
    assert data["result"]["refused"] is True
    assert "operator" in data["next"]["state"]
    assert not any("insert" in sql for sql, _ in cur.executed)


def test_the_bootstrap_token_creates_a_profile_and_hands_back_its_id(monkeypatch):
    cur = RoutingCursor([])
    data = _create(_server(monkeypatch, cur, token=FOUNDER), name="Sam Friend")
    new_id = data["result"]["profile_id"]
    UUID(new_id)                                   # a real id, not a label
    insert = [(s, p) for s, p in cur.executed if "insert into profiles" in s]
    assert len(insert) == 1
    assert new_id in tuple(insert[0][1])
    assert "Sam Friend" in tuple(insert[0][1])
    # the next step is the human hand-over, so the machine's next call is
    # the new owner's first one
    assert data["next"]["call"] == "get_intake_interview"
    assert "mint" in data["next"]["why"]


def test_the_stdio_door_counts_as_the_operator(monkeypatch):
    # No token at all = the local single-user door = the founder himself.
    data = _create(_server(monkeypatch, RoutingCursor([]), token=None))
    assert "profile_id" in data["result"]


def test_the_insert_runs_as_the_new_owner_then_scopes_back(monkeypatch):
    # WITH CHECK (profile_id = app_owner()) means the insert must happen AS
    # the new owner — and the audit row after it must NOT: it belongs to the
    # operator who acted.
    cur = RoutingCursor([])
    data = _create(_server(monkeypatch, cur, token=FOUNDER))
    new_id = data["result"]["profile_id"]
    calls = [(s, p) for s, p in cur.executed]
    adopts = [i for i, (s, _) in enumerate(calls) if "set_config" in s]
    insert = next(i for i, (s, _) in enumerate(calls)
                  if "insert into profiles" in s)
    assert len(adopts) == 2, "adopt the new owner, then scope back"
    assert adopts[0] < insert < adopts[1]
    assert new_id in tuple(calls[adopts[0]][1])
    assert "operator-1" in tuple(calls[adopts[1]][1])


def test_owner_rescope_lives_only_in_the_session_module():
    # The class guard: a set_config anywhere else in the skin is a tool
    # smuggling its own identity past the door.
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path.name == "session.py":
            continue
        if "set_config" in path.read_text():
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"set_config outside session.py: {offenders}"


# ---- the setters: an owner configures their OWN row, secrets stay dark ----


def _call(mcp, tool, args):
    async def go():
        async with Client(mcp) as client:
            return await client.call_tool(tool, args)
    return _run(go()).data


def test_set_notification_channel_never_echoes_the_secret(monkeypatch):
    # The ntfy topic IS the capability to reach the owner's phone. It goes
    # in; it never comes back out — not in the result, not in the audit row.
    topic = "ntfy-topic-Xy77-very-secret"
    cur = FakeCursor(rowcount=1)
    data = _call(_server(monkeypatch, cur, token=FRIEND),
                 "set_notification_channel", {"channel": topic})
    assert data["result"] == {"updated": True}
    import json
    assert topic not in json.dumps(data)
    for sql, params in cur.executed:
        if "mcp_audit" in sql:
            assert topic not in str(params), "the audit row leaked the topic"
    update = [(s, p) for s, p in cur.executed
              if "update profiles" in s and "notification_channel" in s]
    assert len(update) == 1 and topic in tuple(update[0][1])


def test_set_notification_channel_is_honest_about_a_missing_row(monkeypatch):
    data = _call(_server(monkeypatch, FakeCursor(rowcount=0), token=FRIEND),
                 "set_notification_channel", {"channel": "t"})
    assert data["result"] == {"updated": False}


def test_set_notion_token_ref_refuses_a_raw_token(monkeypatch):
    # A reference names a secret; it is never the secret. Notion tokens
    # start ntn_ / secret_ — storing one here would put a credential in a
    # database column that was designed to hold a pointer.
    for raw in ("ntn_abc123", "secret_abc123"):
        cur = FakeCursor(rowcount=1)
        data = _call(_server(monkeypatch, cur, token=FRIEND),
                     "set_notion_token_ref", {"ref": raw})
        assert data["result"]["refused"] is True
        assert not any("update" in s for s, _ in cur.executed)


def test_set_notion_token_ref_stores_a_reference(monkeypatch):
    cur = FakeCursor(rowcount=1)
    data = _call(_server(monkeypatch, cur, token=FRIEND),
                 "set_notion_token_ref", {"ref": "goal-a/notion-sam"})
    assert data["result"] == {"updated": True, "notion_token_ref":
                              "goal-a/notion-sam"}
    update = [(s, p) for s, p in cur.executed if "notion_token_ref" in s]
    assert len(update) == 1


# ---- the database's own refusal (RUN_DB_TESTS=1) ---------------------------

db_tests = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")


@db_tests
def test_the_app_role_cannot_insert_a_profile_for_somebody_else():
    # Seen red by design: without adoption, WITH CHECK refuses the row.
    import psycopg

    from db.connection import get_conn
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("set local role goal_a_app")
                cur.execute("select set_config('app.owner_id', %s, true)",
                            (str(uuid4()),))
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(
                        "insert into profiles (profile_id, name) "
                        "values (%s, %s)", (str(uuid4()), "Refused Row"))
        finally:
            conn.rollback()


@db_tests
def test_an_owner_updates_their_own_channel_and_never_anothers():
    # The database's own refusal, on the real policy: as owner A, updating
    # A's channel touches one row; aiming at B's row touches zero — even
    # when the application layer passes the wrong owner on purpose.
    from criteria.profiles import (insert_profile, set_notification_channel)
    from db.connection import get_conn
    from mcp_server.session import adopt_owner
    a, b = str(uuid4()), str(uuid4())
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("set local role goal_a_app")
                cur.execute("select set_config('app.owner_id', %s, true)",
                            (a,))
                adopt_owner(cur, a)
                insert_profile(cur, a, "Owner A")
                adopt_owner(cur, b)
                insert_profile(cur, b, "Owner B")
                adopt_owner(cur, a)                    # act as A from here
                assert set_notification_channel(cur, a, "topic-a") is True
                assert set_notification_channel(cur, b, "hijack") is False
        finally:
            conn.rollback()


@db_tests
def test_adoption_lets_the_operator_create_the_new_owner_row():
    # Runs the REAL write (criteria.profiles.insert_profile) under the real
    # role and the real policy — the writer-coverage ratchet's demand.
    from criteria.profiles import insert_profile
    from db.connection import get_conn
    from mcp_server.session import adopt_owner
    new_id = str(uuid4())
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("set local role goal_a_app")
                cur.execute("select set_config('app.owner_id', %s, true)",
                            (str(uuid4()),))          # the "operator"
                adopt_owner(cur, new_id)
                row = insert_profile(cur, new_id, "Adopted Test Owner")
                assert row["profile_id"] == new_id
                cur.execute("select count(*) as n from profiles "
                            "where profile_id = %s", (new_id,))
                assert cur.fetchone()["n"] == 1        # visible as the owner
        finally:
            conn.rollback()                            # nothing persists
