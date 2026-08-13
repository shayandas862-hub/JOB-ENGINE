"""Self-serve keys for signed-in owners (Phase 9 task 6).

The friend tier's keys are minted out of band by the founder, which works
exactly as far as the people he has met. Sign-in is what removes him from the
loop, so a signed-in owner mints and revokes their own — and only their own.

Both tools are JWT-only, and the refusals are the design:

* a **minted key** may not mint another. One leaked key would otherwise become
  an unrevokable supply of them: revoking the leaked key does nothing to the
  keys it issued, so the holder keeps the door open through a credential the
  owner never knew existed.
* the **bootstrap token** is refused too. The operator has the mint script,
  which names the owner deliberately; a tool that mints "for whoever is
  calling" means something different in his hands, and the audit trail should
  not have to be read to tell the two apart.
* the **stdio door** is refused. It already has every power it needs without a
  key, and one minted there would be a credential nobody is on the hook for.

Neither tool takes an owner. There is no argument through which a caller could
name somebody else — the owner is the verified identity on the request.
"""
from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token as _token

from audit import record as _audit
from auth.tokens import mint_key, revoke_key_for_owner
from mcp_server.annotations import writes
from mcp_server.contract import with_next
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn

_REFUSAL = ("these tools are for signed-in owners: sign in with Google and "
            "call again with the token that gives you")


def _signed_in() -> bool:
    """Did this caller arrive through a verified sign-in?

    The scope is set by the door and by nothing else (mcp_server.transport),
    which is what makes it safe to read here — a client cannot ask for it.
    """
    token = _token()
    return token is not None and "signed-in" in (token.scopes or [])


def _refused(call: str) -> dict:
    return with_next({"refused": True, "reason": _REFUSAL},
                     state="refused — sign-in required",
                     call=call,
                     why="your current credential already serves your own "
                         "data; it just cannot mint more credentials")


def register(mcp: FastMCP) -> None:
    """Hang the self-serve key tools on the server."""

    @mcp.tool(annotations=writes())
    def issue_my_key(label: str) -> dict:
        """What: mint a long-lived access key for the CALLER'S OWN profile —
        the credential an MCP client stores to reach this engine without
        signing in every time. Signed-in callers only. Shown ONCE, here, and
        never recoverable: the database keeps only its digest.
        When: a signed-in owner is setting up a client, or replacing a key
        they revoked.
        Returns: {key_id, key, label} — or {refused, reason}.
        Next: store the key now; revoke_my_key pulls it if it leaks."""
        if not _signed_in():
            return _refused("daily_brief")
        with get_conn() as conn, conn.cursor() as cur:
            minted = mint_key(cur, _owner(cur), label=label)
            _audit(cur, "issue_my_key", {"label": label},
                   {"key_id": minted["key_id"], "issued": True})
        return with_next(
            minted,
            state="key issued",
            call="daily_brief",
            why="store the key now — it is never shown again; then start "
                "the loop with it")

    @mcp.tool(annotations=writes(idempotent=True))
    def revoke_my_key(key_id: int) -> dict:
        """What: revoke one of the caller's OWN keys. Signed-in callers only.
        The row survives as a stamp. A key id that is not yours answers
        exactly as an unknown one does — this tool will not tell you which
        keys exist. Audited.
        When: a key leaked, a device was lost, or a client was retired.
        Returns: {key_id, outcome: revoked|not_live} — or {refused, reason}.
        Next: issue_my_key if the owner still needs a working client."""
        if not _signed_in():
            return _refused("daily_brief")
        with get_conn() as conn, conn.cursor() as cur:
            outcome = revoke_key_for_owner(cur, key_id, _owner(cur))
            _audit(cur, "revoke_my_key", {"key_id": key_id}, outcome)
        return with_next(
            {"outcome": outcome["outcome"]},
            state=("key revoked" if outcome["outcome"] == "revoked"
                   else "no live key of yours with that id"),
            call="issue_my_key" if outcome["outcome"] == "revoked"
                 else "daily_brief",
            why=("mint a replacement if the owner still needs a client"
                 if outcome["outcome"] == "revoked"
                 else "nothing changed — carry on with the loop"))
