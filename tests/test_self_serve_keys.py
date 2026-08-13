"""Self-serve keys: a signed-in stranger mints their own (Phase 9 task 6).

Until now a key existed only because the founder ran the mint script. That is
the friend tier working as designed — he knows every holder personally. It is
also the thing that does not scale past people he has met, so sign-in brings
its own pair of tools: `issue_my_key` and `revoke_my_key`.

Three properties, each one a way this goes wrong:

* **JWT callers only.** A minted key must not be able to mint another key —
  that turns one leaked key into an unrevokable supply of them, because
  revoking the first does nothing to its children. The bootstrap token is
  refused too: the operator has the mint script, and a tool that mints for
  "whoever the caller is" is a different thing in his hands.
* **The caller's own profile, never a parameter.** Neither tool takes an owner.
  The owner is the verified identity on the request, and there is no argument
  through which a caller could name somebody else.
* **The key value appears exactly once.** In the result of the call that
  created it, and nowhere else — not in the audit row, which records that a
  key was issued and its label, never the secret itself.

Revocation is scoped the same way: another owner's key_id is refused, and the
refusal is deliberately indistinguishable from "no such key" so the tool
cannot be used to discover which key ids exist.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from types import SimpleNamespace

import pytest
from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor

db_tests = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

SIGNED_IN = SimpleNamespace(client_id="signed-in-owner",
                            scopes=["owner", "signed-in"])
FRIEND = SimpleNamespace(client_id="friend-1", scopes=["owner"])
FOUNDER = SimpleNamespace(client_id="operator-1", scopes=["owner", "bootstrap"])


def _run(coro):
    return asyncio.run(coro)


def _server(monkeypatch, cur, token):
    from mcp_server import key_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(key_tools, "get_conn", lambda: fake_conn(cur))
    monkeypatch.setattr(key_tools, "_owner", lambda c: token.client_id)
    monkeypatch.setattr(key_tools, "_token", lambda: token)
    return build_server()


def _call(mcp, tool, args):
    async def go():
        async with Client(mcp) as client:
            return await client.call_tool(tool, args)
    return _run(go()).data


# --- who may mint --------------------------------------------------------

@pytest.mark.parametrize("caller,label", [(FRIEND, "a minted friend key"),
                                          (FOUNDER, "the bootstrap token")])
def test_only_a_signed_in_caller_may_mint_a_key(monkeypatch, caller, label):
    cur = RoutingCursor([])
    data = _call(_server(monkeypatch, cur, caller), "issue_my_key",
                 {"label": "laptop"})
    assert data["result"]["refused"] is True, f"{label} was allowed to mint"
    assert not any("insert into access_keys" in s for s, _ in cur.executed)


def test_the_stdio_door_cannot_mint_either(monkeypatch):
    # No token at all is the local door. It already has every power it needs
    # without a key, and minting one there would produce a credential nobody
    # is on the hook for.
    from mcp_server import key_tools
    from mcp_server.server import build_server
    cur = RoutingCursor([])
    monkeypatch.setattr(key_tools, "get_conn", lambda: fake_conn(cur))
    monkeypatch.setattr(key_tools, "_token", lambda: None)
    monkeypatch.setattr(key_tools, "_owner", lambda c: "local")
    data = _call(build_server(), "issue_my_key", {"label": "laptop"})
    assert data["result"]["refused"] is True


# --- what minting does ---------------------------------------------------

def test_a_signed_in_caller_gets_a_key_for_their_own_profile(monkeypatch):
    cur = RoutingCursor([("insert into access_keys", [{"key_id": 7}])])
    data = _call(_server(monkeypatch, cur, SIGNED_IN), "issue_my_key",
                 {"label": "claude-desktop"})
    result = data["result"]

    assert result["key_id"] == 7
    assert result["key"] and len(result["key"]) > 30
    assert result["label"] == "claude-desktop"
    insert = next(p for s, p in cur.executed if "insert into access_keys" in s)
    assert SIGNED_IN.client_id in tuple(insert), \
        "the key was minted for somebody other than the caller"


def test_the_key_is_shown_once_and_never_recorded(monkeypatch):
    # The audit row proves a key was issued. It must never be the place a
    # leaked key comes from, and neither must the digest.
    cur = RoutingCursor([("insert into access_keys", [{"key_id": 9}])])
    data = _call(_server(monkeypatch, cur, SIGNED_IN), "issue_my_key",
                 {"label": "phone"})
    key = data["result"]["key"]

    audit = [(s, p) for s, p in cur.executed if "mcp_audit" in s]
    assert audit, "issuing a key was not audited at all"
    for _, params in audit:
        assert key not in str(params), "the audit row carries the key value"
    assert json.dumps(data).count(key) == 1, \
        "the key appears more than once in the envelope"
    insert = next(p for s, p in cur.executed if "insert into access_keys" in s)
    assert key not in tuple(insert), "the raw key was stored, not its digest"


def test_the_next_hint_tells_them_to_store_it_now(monkeypatch):
    cur = RoutingCursor([("insert into access_keys", [{"key_id": 1}])])
    data = _call(_server(monkeypatch, cur, SIGNED_IN), "issue_my_key",
                 {"label": "laptop"})
    assert "again" in data["next"]["why"] or "once" in data["next"]["why"]


# --- revocation ----------------------------------------------------------

def test_revoking_is_scoped_to_the_caller_in_the_statement_itself(monkeypatch):
    # Belt and braces: RLS already hides another owner's row from the app
    # role, but the tool must not depend on that alone — a future caller on a
    # different connection would inherit a tool that trusts its argument.
    cur = RoutingCursor([("update access_keys", [{"key_id": 4}])])
    data = _call(_server(monkeypatch, cur, SIGNED_IN), "revoke_my_key",
                 {"key_id": 4})
    update = next((s, p) for s, p in cur.executed if "update access_keys" in s)
    assert "owner_id" in update[0], "the revoke is not scoped by owner"
    assert SIGNED_IN.client_id in tuple(update[1])
    assert data["result"]["outcome"] == "revoked"


def test_revoking_a_key_that_is_not_the_callers_says_nothing_about_it(
        monkeypatch):
    # No row came back. The tool must not tell the caller whether that means
    # "no such key", "already revoked" or "somebody else's" — the three are
    # one answer on purpose.
    cur = RoutingCursor([("update access_keys", [])])
    data = _call(_server(monkeypatch, cur, SIGNED_IN), "revoke_my_key",
                 {"key_id": 999})
    assert data["result"]["outcome"] == "not_live"
    assert "999" not in json.dumps(data["result"])


@pytest.mark.parametrize("caller", [FRIEND, FOUNDER])
def test_only_a_signed_in_caller_may_revoke(monkeypatch, caller):
    cur = RoutingCursor([])
    data = _call(_server(monkeypatch, cur, caller), "revoke_my_key",
                 {"key_id": 1})
    assert data["result"]["refused"] is True
    assert not any("update access_keys" in s for s, _ in cur.executed)


# --- the engine function underneath --------------------------------------

def test_revoke_for_owner_refuses_without_matching_the_owner():
    from auth.tokens import revoke_key_for_owner
    cur = FakeCursor(rows=[])
    out = revoke_key_for_owner(cur, 3, "owner-a")
    assert out["outcome"] == "not_live"
    sql, params = cur.executed[0]
    assert "owner_id = %s" in sql and "owner-a" in tuple(params)


# --- against the real database -------------------------------------------

@db_tests
def test_one_owner_cannot_revoke_anothers_key():
    # The adversarial proof, on the real table under the real policy: B aims
    # at A's key_id and A's key is still live afterwards.
    from auth.tokens import (list_keys, mint_key, owner_for_key,
                             revoke_key_for_owner)
    from criteria.profiles import insert_profile
    from db.connection import get_conn
    from mcp_server.session import adopt_owner

    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("set local role goal_a_app")
                adopt_owner(cur, a)
                insert_profile(cur, a, "Key Owner A")
                a_key = mint_key(cur, a, label="a-laptop")
                adopt_owner(cur, b)
                insert_profile(cur, b, "Key Owner B")

                # B, acting as B, tries to pull A's key
                stolen = revoke_key_for_owner(cur, a_key["key_id"], b)
                assert stolen["outcome"] == "not_live"

                # and A's key still opens the door
                adopt_owner(cur, a)
                assert owner_for_key(cur, a_key["key"]) == a
                live = [k for k in list_keys(cur, a) if k["revoked_at"] is None]
                assert len(live) == 1, "A's key was revoked by somebody else"

                # the control: A can revoke their own
                assert revoke_key_for_owner(
                    cur, a_key["key_id"], a)["outcome"] == "revoked"
                assert owner_for_key(cur, a_key["key"]) is None
        finally:
            conn.rollback()
