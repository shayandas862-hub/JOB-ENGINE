"""Record every Claude action in mcp_audit — provisional-until-confirmed for the AI.

One row per action, written in the action's own transaction so the trail exactly
reflects what committed. Stores an arg summary and a result summary; the action
tools pass non-secret args and secret-free results, so no secret ever lands here.
"""
from __future__ import annotations

import json


def record(cur, tool: str, args: dict | None, result) -> None:
    """Insert one audit row. args/result are summarised as JSON; default=str keeps
    a stray date/Decimal from raising."""
    cur.execute(
        "insert into mcp_audit (tool, args, result) values (%s,%s,%s)",
        (tool,
         json.dumps(args, default=str) if args is not None else None,
         json.dumps(result, default=str) if result is not None else None))
