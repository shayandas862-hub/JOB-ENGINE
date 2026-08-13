"""Tool annotations — the four MCP behaviour hints, defined once (M3).

Every tool shipped with ``annotations=None``, so a client could not tell
``get_job`` from ``mark_applied`` except by reading prose. That blocks the one
thing the hints exist for: letting a client run reads without stopping to ask
the owner, and stopping on everything else.

The rules, applied literally — each tool's decorator is the claim, and
tests/test_mcp_door.py is the check on it:

  read       the call writes NOTHING — no row, no stamp, no audit trail, no
             spawned script. Safe to run unasked.
  destructive  it withdraws something the owner cannot restore through this
             same door. Overwriting a value they can simply set back is not
             destructive.
  idempotent   calling again with the same arguments leaves the same state
             (a stamp, an upsert, a no-op). A call that adds a row, renders a
             document or sends a push each time is not.
  open_world   the call reaches outside the database — a fetch, a push, or a
             detached script that does one.

The protocol reads destructive/idempotent only on a write, so ``READ`` states
just the two that mean anything on a read.
"""
from __future__ import annotations

READ = {"readOnlyHint": True, "openWorldHint": False}


def writes(*, destructive: bool = False, idempotent: bool = False,
           open_world: bool = False) -> dict:
    """The annotation set for a tool that changes something.

    Every hint is stated: an unset destructiveHint falls back to the
    protocol's default of *true*, which would have the client asking the
    owner about every call again.
    """
    return {"readOnlyHint": False, "destructiveHint": destructive,
            "idempotentHint": idempotent, "openWorldHint": open_world}
