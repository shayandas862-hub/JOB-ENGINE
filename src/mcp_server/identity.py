"""Whose data is this call for? — one answer, one place (Phase 9 task 1).

Every tool used to ask the database for its first profile
(``default_profile_id``). With one user that was correct; with two it hands
the second one the first one's data, through every tool at once. So the
question moves to the door: the verifier resolved the presented key to an
owner, and this reads that owner back.

The fallback is deliberate and narrow. No verified caller means stdio — the
local, single-user door that carries no auth by design — and there the first
profile IS the owner. That is the ONLY place ``default_profile_id`` may still
be reached from the skin, which tests/test_mcp_identity.py enforces.

Resolution is not authorisation. Knowing the caller is user B does nothing on
its own; every query still has to be scoped to B, and the database still has
to refuse B's reach for A's rows. Those are the rest of task 1 and task 2.
"""
from __future__ import annotations

from fastmcp.server.dependencies import get_access_token

from criteria.loader import default_profile_id


def current_owner(cur) -> str:
    """The owner this call is for: the verified caller, else the local one.

    Always a plain string. The token path already carries one (the key lookup
    casts ``owner_id::text``); the fallback does not — profile_id is a uuid
    column, so psycopg hands back a ``uuid.UUID``. One type out means callers
    never have to care which door they came through.
    """
    token = get_access_token()
    if token is not None and token.client_id:
        return token.client_id
    return str(default_profile_id(cur))
