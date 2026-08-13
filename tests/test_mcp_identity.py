"""Who is this call for? — the door's owner resolution (Phase 9 task 1).

Until now the answer was a constant: the verifier stamped every request
``client_id="founder"`` and every tool asked the database for its first
profile. Both are the same single-user assumption wearing two hats, and both
have to go before a second person can hold a key.

The seam is deliberately small: the verifier turns a presented key into an
owner id, and ``current_owner`` reads that owner back inside a tool —
falling back to the local profile ONLY when there is no verified caller at
all, which is stdio, the single-user local door.

Offline: no DB, no network, no HTTP server.
"""
from __future__ import annotations

import asyncio
import uuid

from tests.conftest import FakeCursor, fake_conn

OWNER_A = "11111111-1111-4111-a111-111111111111"
OWNER_B = "22222222-2222-4222-a222-222222222222"

# profiles.profile_id is a uuid column and psycopg3 loads it as a uuid.UUID —
# so default_profile_id hands back a UUID OBJECT, whatever its annotation
# says. Faking it as a str made every test on the bootstrap path unable to
# fail; the real hosted door raised a pydantic ValidationError and returned
# 500. The fakes below return the real type on purpose.
LOCAL_PROFILE = uuid.UUID(OWNER_A)


def _verify(verifier, key):
    return asyncio.run(verifier.verify_token(key))


def _verifier(monkeypatch, *, resolves_to, bootstrap="",
              first_profile=LOCAL_PROFILE):
    """A verifier whose database answers exactly what the test wants."""
    from mcp_server import transport
    monkeypatch.setattr(transport, "get_conn",
                        lambda: fake_conn(FakeCursor(rows=[])))
    monkeypatch.setattr(transport, "owner_for_key",
                        lambda cur, key: resolves_to)
    monkeypatch.setattr(transport, "default_profile_id",
                        lambda cur: first_profile)
    return transport.BearerVerifier(bootstrap)


# --- the verifier: a key names its owner --------------------------------

def test_a_verified_key_carries_the_owner_it_belongs_to(monkeypatch):
    # The whole task in one assertion: the identity on the request is user B's
    # own id, not the word "founder" and not the first row in profiles.
    granted = _verify(_verifier(monkeypatch, resolves_to=OWNER_B), "b-key")
    assert granted is not None
    assert granted.client_id == OWNER_B
    assert granted.client_id != "founder"


def test_a_key_that_belongs_to_nobody_is_refused(monkeypatch):
    assert _verify(_verifier(monkeypatch, resolves_to=None), "stolen") is None


def test_no_key_at_all_is_refused_without_touching_the_database(monkeypatch):
    from mcp_server import transport
    calls = []
    monkeypatch.setattr(transport, "get_conn",
                        lambda: calls.append(1) or fake_conn(FakeCursor()))
    assert _verify(transport.BearerVerifier("boot"), "") is None
    assert _verify(transport.BearerVerifier("boot"), None) is None
    assert calls == []


def test_the_bootstrap_key_is_the_only_one_that_means_the_local_profile(monkeypatch):
    # The founder's existing MCP_TOKEN keeps working — it resolves to the
    # first profile, which is his. It is an operator key, named as such, and
    # it is the ONLY path that guesses an owner rather than being told one.
    # The profile id arrives as a uuid.UUID (see LOCAL_PROFILE): the identity
    # on the request must still be a plain string, because AccessToken
    # declares client_id: str and pydantic refuses anything else.
    verifier = _verifier(monkeypatch, resolves_to=None, bootstrap="boot-key")
    granted = _verify(verifier, "boot-key")
    assert granted is not None and granted.client_id == OWNER_A
    assert isinstance(granted.client_id, str)
    assert "bootstrap" in granted.scopes

    # and it admits nothing else
    assert _verify(verifier, "boot-key ") is None      # no trimming games
    assert _verify(verifier, "other") is None


def test_a_minted_key_wins_over_the_bootstrap(monkeypatch):
    # If a key is in the table, its stored owner decides — the bootstrap can
    # never override a real key's owner.
    verifier = _verifier(monkeypatch, resolves_to=OWNER_B, bootstrap="boot-key")
    granted = _verify(verifier, "boot-key")
    assert granted.client_id == OWNER_B


def test_with_no_bootstrap_configured_only_minted_keys_open_the_door(monkeypatch):
    assert _verify(_verifier(monkeypatch, resolves_to=None, bootstrap=""),
                   "anything") is None


# --- current_owner: the tools read the verified caller ------------------

def test_current_owner_is_the_verified_caller_not_the_first_profile(monkeypatch):
    # A tool must never learn the owner by asking the database which profile
    # is oldest — that is the single-user assumption, and it hands user B
    # user A's data.
    from mcp_server import identity

    class _Token:
        client_id = OWNER_B
    monkeypatch.setattr(identity, "get_access_token", lambda: _Token())
    cur = FakeCursor(rows=[{"profile_id": OWNER_A}])

    assert identity.current_owner(cur) == OWNER_B
    assert cur.executed == [], "the owner came from the DB, not the token"


def test_current_owner_falls_back_to_the_local_profile_under_stdio(monkeypatch):
    # stdio is the local single-user door: no auth, no token, one profile.
    # The DB hands back a uuid.UUID; tools get one type either way.
    from mcp_server import identity
    monkeypatch.setattr(identity, "get_access_token", lambda: None)
    cur = FakeCursor(rows=[{"profile_id": LOCAL_PROFILE}])
    owner = identity.current_owner(cur)
    assert owner == OWNER_A and isinstance(owner, str)
    assert cur.executed, "the fallback never asked the DB for a profile"


def test_outside_a_request_there_is_genuinely_no_token():
    # Proves the fallback above is the real default rather than a monkeypatch
    # artefact: the actual FastMCP dependency returns None when nobody is
    # authenticated.
    from fastmcp.server.dependencies import get_access_token
    assert get_access_token() is None


def test_every_tool_module_resolves_its_owner_through_the_door():
    # The seam is only worth having if nothing bypasses it. No tool module may
    # call default_profile_id directly any more — that helper is now the
    # fallback INSIDE current_owner and nowhere else.
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "mcp_server"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name in ("identity.py", "transport.py"):
            continue          # the two places allowed to know the fallback
        text = path.read_text()
        if "default_profile_id" in text:
            offenders.append(path.name)
    assert offenders == [], \
        f"tool modules bypassing current_owner: {offenders}"
