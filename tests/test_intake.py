"""src/cv/intake.py + the get_intake_interview door (Phase 9 task 4 / M1).

A new user's fact base is built through a SERVED, versioned interview —
intake-v1 — on the same pattern as extract-v1 and cv-v1: the engine owns
the prompt and whichever AI the user brings just complies. Before this,
every client wrote its own interview questions, so fact-base quality was
unversioned and unknowable (plan 0013 §6 M1 — "it decides user #2's data
quality forever").
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor


def _counts_cursor(blocks=0, confirmed=0):
    return RoutingCursor([
        ("from cv_blocks", [{"blocks": blocks, "confirmed": confirmed}]),
    ])


def test_intake_is_versioned_server_side_data():
    from cv.intake import PROMPT_VERSION, get_interview
    out = get_interview(_counts_cursor(), "owner-1")
    # v2 since Phase 9.5 task 3 (M7). Bumped deliberately, not edited in
    # place: the instructions materially changed — one call now records a
    # fact and the skills it evidences together, where v1 asked for two
    # independent calls and the two vocabularies drifted apart on real data.
    # A client that reads "intake-v1" is entitled to what v1 described, which
    # is the entire reason the prompt carries a version.
    assert out["prompt_version"] == PROMPT_VERSION == "intake-v2"
    assert out["prompt"]                     # served, never client-invented


def test_intake_prompt_carries_the_interview_rules():
    # The rules M1 exists for: one fact per block; dates and numbers asked
    # for; honest tool levels; drafts-only with the owner confirming; life
    # outside paid work on the same footing; nothing invented.
    from cv.intake import INTERVIEW_PROMPT
    p = INTERVIEW_PROMPT.lower()
    assert "one fact" in p
    assert "date" in p and "number" in p
    assert "honest" in p
    assert "draft" in p and "confirm" in p
    assert "never" in p
    assert "outside paid work" in p


def test_intake_shape_stays_in_lockstep_with_the_writer_quartet():
    # The interview's required shape IS add_cv_block's signature — pinned
    # against the writer's own whitelist so the two can never drift apart.
    from cv.blocks import BLOCK_KINDS
    from cv.intake import REQUIRED_SHAPE
    fact = REQUIRED_SHAPE["facts"]
    for field in ("kind", "fact_text", "title", "organisation",
                  "date_range", "skill_norms"):
        assert field in fact, f"facts shape lost {field}"
    for kind in BLOCK_KINDS:
        assert kind in fact["kind"], f"kind list lost {kind}"
    skills = REQUIRED_SHAPE["skills"]
    assert "learned_at" in skills and "evidence" in skills


def test_intake_reports_the_fact_base_state():
    from cv.intake import get_interview
    fresh = get_interview(_counts_cursor(0, 0), "owner-1")
    assert fresh["fact_base"] == {"blocks": 0, "confirmed": 0, "drafts": 0}
    grown = get_interview(_counts_cursor(22, 20), "owner-1")
    assert grown["fact_base"] == {"blocks": 22, "confirmed": 20, "drafts": 2}


def test_intake_counts_only_the_owners_unretired_blocks():
    from cv.intake import get_interview
    cur = _counts_cursor(3, 1)
    get_interview(cur, "owner-1")
    sql, params = [(s, p) for s, p in cur.executed
                   if "from cv_blocks" in s.lower()][0]
    assert "owner_id" in sql and "retired_at is null" in sql
    assert "owner-1" in tuple(params or ())


# ---- the MCP door -----------------------------------------------------------

INTERVIEW = {"prompt_version": "intake-v1", "prompt": "…",
             "required_shape": {}, "coverage": [],
             "fact_base": {"blocks": 0, "confirmed": 0, "drafts": 0}}


def _run(coro):
    return asyncio.run(coro)


def _server(monkeypatch, interview):
    from mcp_server import onboarding_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(onboarding_tools, "get_conn",
                        lambda: fake_conn(FakeCursor(rows=[])))
    monkeypatch.setattr(onboarding_tools, "_owner", lambda c: "p1")
    monkeypatch.setattr(onboarding_tools, "get_interview",
                        lambda cur, owner: interview)
    return build_server()


def test_get_intake_interview_points_a_fresh_user_at_the_first_fact(monkeypatch):
    mcp = _server(monkeypatch, INTERVIEW)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_intake_interview", {})
            data = r.data
            assert set(data.keys()) == {"result", "next"}
            assert data["result"]["prompt_version"] == "intake-v1"
            assert data["next"]["call"] == "add_cv_block"
    _run(go())


def test_get_intake_interview_routes_open_drafts_to_the_owner(monkeypatch):
    drafts = dict(INTERVIEW,
                  fact_base={"blocks": 5, "confirmed": 2, "drafts": 3})
    mcp = _server(monkeypatch, drafts)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_intake_interview", {})
            assert r.data["next"]["call"] == "list_cv_blocks"
    _run(go())
