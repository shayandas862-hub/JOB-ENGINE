"""M4 — typed outputs on the loop tools, and ONLY there (Phase 9 task 4).

Plan 0013 §6: every tool shipped with output schema
`{"type": "object", "additionalProperties": true}`, so a client could not
validate what it receives — the shape lived only in Returns: prose. The fix
is deliberately partial: the six tools of the daily loop declare the
envelope and their result's stable core; the other tools keep prose,
because full typing of the whole surface is churn the contract-v2 `next`
block does not need. The boundary is the tested thing.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

LOOP_SIX = {"daily_brief", "get_reading_batch", "submit_reading",
            "serve_cv", "submit_cv", "get_apply_queue"}


def _tools():
    from mcp_server.server import build_server

    async def go():
        async with Client(build_server()) as client:
            return {t.name: t for t in await client.list_tools()}
    return asyncio.run(go())


def test_the_loop_six_declare_the_envelope_and_their_result_core():
    tools = _tools()
    for name in LOOP_SIX:
        schema = tools[name].outputSchema
        props = (schema or {}).get("properties", {})
        assert set(props) == {"result", "next"}, \
            f"{name}: the envelope is the schema's outer shape"
        nxt = props["next"]
        assert set(nxt["properties"]) == {"state", "call", "why"}, \
            f"{name}: the next block is the contract"
        assert nxt["required"] == ["state", "call", "why"]
        # the result half must say SOMETHING a client can validate — a bare
        # permissive object is exactly the state M4 exists to end
        result = props["result"]
        assert result.get("properties") or result.get("type") == "array", \
            f"{name}: result is still an untyped object"


def test_typing_stops_exactly_at_the_loop_six():
    # The deliberate boundary: everything else keeps the generic object —
    # a 46th typed tool is a decision for a future phase, not drift.
    tools = _tools()
    for name, tool in tools.items():
        if name in LOOP_SIX:
            continue
        props = (tool.outputSchema or {}).get("properties", {})
        assert "next" not in props, \
            f"{name}: gained a typed envelope outside the M4 boundary"
