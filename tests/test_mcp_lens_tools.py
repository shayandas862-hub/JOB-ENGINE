"""The lens tools (Phase 8.5 / U2), driven through the real in-process client.

find_industry_codes is the words→codes translator; add_skill is the
owner-scoped skills entry. Together with set_promotion_rule (already live)
they make a lens settable by conversation alone — zero operator SQL. The DB
is mocked; nothing is written.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor


def _run(coro):
    return asyncio.run(coro)


def _server(monkeypatch, cur):
    from mcp_server import lens_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(lens_tools, "get_conn", lambda: fake_conn(cur))
    return build_server()


def test_find_industry_codes_serves_ranked_candidates(monkeypatch):
    cur = RoutingCursor([
        ("from sic_codes", [
            {"code": "88100",
             "description": "Home care services for the elderly and disabled"},
            {"code": "87300",
             "description": "Residential care activities for the elderly and disabled"},
        ]),
        ("from sponsor_census", [{"code": "87300", "sponsors": 3911},
                                 {"code": "88100", "sponsors": 1500}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("find_industry_codes",
                                       {"words": "care homes"})
            cands = r.data["result"]["candidates"]
            assert cands[0]["code"] == "88100"          # both tokens matched
            assert cands[0]["sponsors"] == 1500
            # the confirmed codes get written by the EXISTING rule tool —
            # the translator itself never writes
            assert r.data["next"]["call"] == "set_promotion_rule"
    _run(go())


def test_find_industry_codes_with_no_match_says_try_other_words(monkeypatch):
    cur = RoutingCursor([("from sic_codes", [])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("find_industry_codes", {"words": "zzz"})
            assert r.data["result"]["candidates"] == []
            assert r.data["next"]["call"] == "find_industry_codes"
    _run(go())


def test_add_skill_writes_owner_scoped_and_audits(monkeypatch):
    cur = FakeCursor(rows=[{"profile_id": "owner-1"}], rowcount=0)
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("add_skill", {
                "skill": "Care Planning", "level": "working",
                "evidence": "2 years at Meadow House",
                "learned_at": "2024-03-01"})
            assert r.data["result"]["outcome"] == "added"
            assert r.data["result"]["skill_norm"] == "care planning"
            executed = [s for s, _ in cur.executed]
            assert any("insert into my_skills" in s.lower() for s in executed)
            assert any("insert into mcp_audit" in s.lower() for s in executed)
            assert r.data["next"]["call"] == "get_skill_gaps"
    _run(go())


def test_add_skill_reports_a_bad_date_as_a_tool_error(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[{"profile_id": "owner-1"}]))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("add_skill",
                                       {"skill": "Python",
                                        "learned_at": "last spring"},
                                       raise_on_error=False)
            assert r.is_error
    _run(go())


# ---- U3: the universal searches ---------------------------------------------

def test_search_sponsors_tool_serves_the_universal_census_search(monkeypatch):
    row = {"org_name_norm": "sunrise care ltd",
           "organisation_name": "Sunrise Care Ltd", "town_city": "Leeds",
           "registry_status": "active", "industry_codes": ["87300"],
           "industry_descriptions": ["Residential care activities"],
           "probe_outcome": "board_found", "careers_url": "https://x",
           "local_jobs_seen": 3, "total_jobs_seen": 5}
    cur = RoutingCursor([("from v_sponsor_industry", [row])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "search_sponsors",
                {"industry_words": "care homes", "town": "Leeds",
                 "with_boards_only": True})
            assert r.data["result"]["sponsors"][0]["town_city"] == "Leeds"
            assert r.data["next"]["call"] == "promote_company"
    _run(go())


def test_search_sponsors_empty_result_hints_the_knock(monkeypatch):
    cur = RoutingCursor([("from v_sponsor_industry", [])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("search_sponsors",
                                       {"industry_words": "zzz"})
            assert r.data["result"]["sponsors"] == []
            assert r.data["next"]["call"] == "find_industry_codes"
    _run(go())


def test_search_hiring_tool_answers_who_is_hiring(monkeypatch):
    tracked = {"role_id": 917, "title": "Care Assistant",
               "company_name": "Sunrise Care", "location": "Leeds",
               "role_url": "https://x/1", "salary_text": None,
               "source": "tracked"}
    cur = RoutingCursor([("from role_listings", [tracked]),
                         ("from census_jobs", [])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("search_hiring",
                                       {"role_words": "care assistant"})
            jobs = r.data["result"]["jobs"]
            assert jobs[0]["source"] == "tracked"
            assert r.data["next"]["call"] == "get_job"
    _run(go())
