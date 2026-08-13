"""The serve-all CV pair (task 0 / U8), through the real in-process client.

serve_cv hands the client AI the job + EVERY confirmed fact + the cv-v1
prompt; submit_cv returns the written CV through the truth gate and the
ENGINE renders the .docx. The DB is mocked; the docx bytes are real.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor
from tests.test_cv_serve_all import BLOCKS, JOB


def _run(coro):
    return asyncio.run(coro)


def _server(monkeypatch, cur):
    from mcp_server import cv_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(cv_tools, "get_conn", lambda: fake_conn(cur))
    return build_server()


def test_serve_cv_tool_hands_over_the_whole_fact_base(monkeypatch):
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from role_listings r join target_companies", [JOB]),
        ("from cv_blocks", BLOCKS),
        ("from role_skills", [{"skill_norm": "python"}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("serve_cv", {"role_id": 917})
            assert len(r.structured_content["result"]["blocks"]) == 2      # ALL served
            assert r.structured_content["result"]["prompt_version"] == "cv-v1"
            assert r.structured_content["next"]["call"] == "submit_cv"
    _run(go())


def test_submit_cv_tool_renders_audits_and_points_at_apply(monkeypatch):
    from mcp_server import cv_tools
    monkeypatch.setattr(
        cv_tools, "_accept",
        lambda cur, owner, role_id, cv: {
            "outcome": "rendered", "role_id": role_id, "used": 2,
            "fallbacks": 1, "rejected_block_ids": [], "docx": b"PK-bytes",
            "cv_path": "/cvs/cv-917.docx", "card_url": None})
    cur = FakeCursor(rows=[{"profile_id": "owner-1"}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "submit_cv",
                {"role_id": 917,
                 "cv": {"blocks": [{"block_id": 1, "bullet": "x"}]}})
            payload = r.structured_content["result"]
            assert payload["outcome"] == "rendered"
            assert payload["cv_path"] == "/cvs/cv-917.docx"
            assert "docx" not in payload            # bytes never ride the wire
            assert any("insert into mcp_audit" in s.lower()
                       for s, _ in cur.executed)
            assert r.structured_content["next"]["call"] == "mark_applied"
    _run(go())


def test_serve_cv_with_no_blocks_says_seed_first(monkeypatch):
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from role_listings r join target_companies", [JOB]),
        ("from cv_blocks", []),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("serve_cv", {"role_id": 917})
            assert r.structured_content["result"]["outcome"] == "no_blocks"
            assert r.structured_content["next"]["call"] == "daily_brief"
    _run(go())


# ---- U8b: the cv_blocks writer quartet --------------------------------------

def test_add_cv_block_tool_drafts_and_audits(monkeypatch):
    # FakeCursor serves the same row to every fetch — one merged row covers
    # the owner lookup and the returning block_id.
    cur = FakeCursor(rows=[{"profile_id": "owner-1", "block_id": 44}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("add_cv_block", {
                "kind": "achievement",
                "fact_text": "Shipped the rota tool to 40 staff.",
                "title": "Rota tool", "skill_norms": ["python"]})
            assert r.structured_content["result"]["confirmed"] is False    # a DRAFT
            assert r.structured_content["next"]["call"] == "confirm_cv_block"
            assert any("insert into mcp_audit" in s.lower()
                       for s, _ in cur.executed)
    _run(go())


def test_confirm_and_retire_tools_round_trip(monkeypatch):
    cur = FakeCursor(rows=[{"profile_id": "owner-1"}], rowcount=1)
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("confirm_cv_block", {"block_id": 44})
            assert r.structured_content["result"]["outcome"] == "confirmed"
            r = await client.call_tool("retire_cv_block", {"block_id": 44})
            assert r.structured_content["result"]["outcome"] == "retired"
    _run(go())


def test_list_cv_blocks_serves_both_states_for_approval(monkeypatch):
    rows = [{"block_id": 1, "kind": "role", "title": "T", "organisation": "O",
             "date_range": "2024", "fact_text": "F", "skill_norms": [],
             "sort_hint": 0, "confirmed": True, "retired_at": None},
            {"block_id": 2, "kind": "achievement", "title": None,
             "organisation": None, "date_range": None, "fact_text": "Draft",
             "skill_norms": [], "sort_hint": 1, "confirmed": False,
             "retired_at": None}]
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from cv_blocks", rows),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("list_cv_blocks", {})
            got = r.structured_content["result"]["blocks"]
            assert [b["confirmed"] for b in got] == [True, False]
    _run(go())
