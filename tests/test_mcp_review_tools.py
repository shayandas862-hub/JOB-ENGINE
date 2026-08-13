"""The two review tools, driven through the in-process MCP client (DB mocked)."""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn


def _run(coro):
    return asyncio.run(coro)


# The owner these tools resolve to, pinned so a query's parameters can be
# checked for carrying it (owner resolution itself is proven in
# tests/test_mcp_identity.py).
CALLER = "cccccccc-cccc-4ccc-accc-cccccccccccc"


def _server(monkeypatch, cur, owner: str = CALLER):
    from mcp_server import review_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(review_tools, "get_conn", lambda: fake_conn(cur))
    monkeypatch.setattr(review_tools, "_owner", lambda cur: owner)
    return build_server()


def test_both_review_tools_are_registered(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
            assert {"list_review_flags", "resolve_review_flag"} <= names
    _run(go())


def test_list_review_flags_returns_the_open_queue(monkeypatch):
    rows = [{"review_id": 1, "kind": "skill_synonym", "ref": "k8s",
             "summary": "Low-confidence synonym", "evidence": {"raw_norm": "k8s"},
             "status": "open", "created_at": "2026-07-11T00:00:00", "resolved_at": None}]
    mcp = _server(monkeypatch, FakeCursor(rows=rows))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("list_review_flags", {})
            assert r.data["result"][0]["review_id"] == 1
            assert r.data["result"][0]["evidence"]["raw_norm"] == "k8s"    # jsonb preserved
    _run(go())


def test_resolve_review_flag_records_the_decision(monkeypatch):
    cur = FakeCursor(rows=[{"review_id": 1, "kind": "skill_synonym", "status": "resolved"}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "resolve_review_flag",
                {"review_id": 1, "resolution": {"decision": "accept"}})
            assert r.data["result"]["status"] == "resolved"
            assert any("update review_items" in e[0].lower() for e in cur.executed)
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_resolve_review_flag_returns_null_when_not_open(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("resolve_review_flag", {"review_id": 999})
            assert r.data["result"] is None
    _run(go())
