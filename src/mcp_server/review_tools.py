"""Review tools — the two wrappers a client AI uses to work the review queue.

Thin skin over src/review, wrapped in the contract-v2 envelope: list the
ambiguities the engine couldn't decide, and record a decision on one. Filled
by discovery (sponsor_match), the nightly promotion rule (promotion_review),
and low-confidence skill synonyms.
"""
from __future__ import annotations

from fastmcp import FastMCP

from audit import record as _audit
from mcp_server.annotations import READ, writes
from mcp_server.contract import with_next
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn
from review import list_flags as _list_flags
from review import resolve_flag as _resolve_flag


def register(mcp: FastMCP) -> None:
    """Hang the two review tools on the server."""

    @mcp.tool(annotations=READ)
    def list_review_flags(status: str = "open", limit: int = 50) -> dict:
        """What: ambiguities the engine refused to guess at — borderline
        promotions, unclear sponsor matches, low-confidence synonyms — each
        carrying its evidence.
        When: daily_brief reports open flags, or after a discovery run.
        Returns: up to `limit` flags with the given status (open | resolved |
        dismissed).
        Next: resolve_review_flag(review_id, resolution) on each."""
        with get_conn() as conn, conn.cursor() as cur:
            rows = _list_flags(cur, _owner(cur), status, limit)
        if rows and status == "open":
            return with_next(rows, state=f"{len(rows)} open flags",
                             call="resolve_review_flag",
                             why="settle each with a decision the engine records")
        return with_next(rows, state=f"{len(rows)} {status} flags",
                         call="daily_brief", why="back to the agenda")

    @mcp.tool(annotations=writes(idempotent=True))
    def resolve_review_flag(review_id: int, resolution: dict | None = None,
                            dismiss: bool = False) -> dict:
        """What: resolve (or dismiss) one review flag, recording your
        decision as the flag's resolution.
        When: after judging a flag from list_review_flags — the human's or
        AI's call, on the record.
        Returns: the updated flag, or null if it wasn't open (resolving
        twice is a harmless no-op).
        Next: list_review_flags for the next one."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _resolve_flag(cur, _owner(cur), review_id, resolution,
                                   dismiss)
            if result is not None:      # only a real resolution is an auditable action
                _audit(cur, "resolve_review_flag",
                       {"review_id": review_id, "dismiss": dismiss}, result)
        return with_next(
            result,
            state="resolved" if result is not None else "was not open",
            call="list_review_flags", why="work the next flag")
