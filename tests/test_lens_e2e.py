"""The Phase 8.5 acceptance: a care-home lens by conversation alone (task 6).

One integration walk over the REAL in-process MCP server: the words become
rows, the rows drive every engine surface, and not one industry-specific
branch exists anywhere in the chain — the same functions serve the founder's
software lens and a care lens with nothing but different rows. The DB is
routed; the live-data twin of this walk (read-only, measured 2026-08-10) is
recorded in the progress log.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor

CARE_CODES = ["87300", "87100", "87900", "86102"]


def _run(coro):
    return asyncio.run(coro)


def test_step1_words_become_ranked_codes_over_mcp(monkeypatch):
    # "care homes" -> ranked SIC candidates with sponsor counts. No SQL from
    # the operator, no code edit — the translator tool alone.
    from mcp_server import lens_tools
    from mcp_server.server import build_server
    cur = RoutingCursor([
        ("from sic_codes", [
            {"code": "87300",
             "description": "Residential care activities for the elderly and disabled"},
            {"code": "87100",
             "description": "Residential nursing care facilities"}]),
        ("from sponsor_census", [{"code": "87300", "sponsors": 1772},
                                 {"code": "87100", "sponsors": 1099}]),
    ])
    monkeypatch.setattr(lens_tools, "get_conn", lambda: fake_conn(cur))
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("find_industry_codes",
                                       {"words": "care homes"})
            codes = [c["code"] for c in r.data["result"]["candidates"]]
            assert "87300" in codes and "87100" in codes
            assert r.data["next"]["call"] == "set_promotion_rule"
    _run(go())


def test_step2_confirmed_codes_become_the_lens_row_and_knock(monkeypatch):
    # set_promotion_rule writes the rule AND starts the door-knock for the
    # new lens — the 0.7%-coverage slice does not wait for anyone.
    from mcp_server import loop_tools
    from mcp_server.server import build_server
    old = {"industry_codes": ["62012"], "min_local_jobs": 1, "auto": True,
           "adzuna_category": "it-jobs"}
    new = {"industry_codes": CARE_CODES, "min_local_jobs": 1, "auto": True,
           "adzuna_category": "social-work-jobs"}
    knocks = []
    monkeypatch.setattr(loop_tools, "get_conn",
                        lambda: fake_conn(FakeCursor()))
    monkeypatch.setattr(loop_tools, "_owner", lambda c: "care-owner")
    monkeypatch.setattr(loop_tools, "load_rule", lambda c, o: old)
    monkeypatch.setattr(loop_tools, "save_rule",
                        lambda c, o, **kw: {"owner_id": o, **new})
    monkeypatch.setattr(loop_tools, "_spawn_knock",
                        lambda owner: knocks.append(owner) or "/logs/knock.log")
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "set_promotion_rule",
                {"industry_codes": CARE_CODES,
                 "adzuna_category": "social-work-jobs"})
            assert r.data["result"]["industry_codes"] == CARE_CODES
            assert r.data["result"]["knock"]["started"] is True
            assert knocks == ["care-owner"]
    _run(go())


def test_step3_the_same_picker_now_picks_care_cards():
    # Pass-2 probing under the stored rule: care cards, no code edit — the
    # keystone (U1) exercised by the whole-chain rule row.
    from discover.probe_pick import pick_owner_lens_batch
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "care-owner"}]),
        ("from promotion_rules", [{"industry_codes": CARE_CODES,
                                   "min_local_jobs": 1, "auto": True}]),
        ("from sponsor_census", [{"org_name_norm": "sunrise care ltd"}]),
    ])
    out = pick_owner_lens_batch(cur, 100)
    assert out == [{"org_name_norm": "sunrise care ltd"}]
    params = [p for s, p in cur.executed if "from sponsor_census" in s.lower()][0]
    assert params["codes"] == CARE_CODES


def test_step4_the_tray_serves_care_titles_under_care_patterns():
    # The staging sieve under care target_roles: a care title is a MATCH; a
    # software title is at most a labelled near-miss the AI may skip.
    from reading.stage import stage_ready
    from tests.conftest import ScriptedCursor
    cur = ScriptedCursor([
        ("from profiles", [[{"profile_id": "care-owner", "name": "C"}]]),
        ("from my_constraints", [[]]),
        ("from target_roles", [[{"search_title": "Care Assistant"},
                                {"search_title": "Support Worker"}]]),
        ("select r.role_id, r.role_title from role_listings", [[
            {"role_id": 1, "role_title": "Senior Care Assistant (Nights)"},
            {"role_id": 2, "role_title": "Software Engineer"}]]),
        ("update role_listings set staged_at", [[]]),
    ])
    result = stage_ready(cur, "care-owner")
    assert result == {"candidates": 2, "staged": 1, "near_miss": 1}
    stamped = {p[0]: p[1] for s, p in cur.executed
               if "set staged_at" in s.lower()}
    assert stamped == {"match": [1], "near_miss": [2]}


def test_step5_no_engine_surface_hardcodes_the_software_lens():
    # The negative proof: the words that would pin the machine to the
    # founder's industry appear nowhere in the universal chain's sources.
    import inspect

    from criteria import lens
    from discover import probe_pick
    from fetch import jd_drip
    from reading import stage
    for module in (lens, probe_pick, stage, jd_drip):
        source = inspect.getsource(module).lower()
        # SOFTWARE_SIC may appear ONLY as probe_pick's documented rule-less
        # bootstrap fallback; no other industry constant may exist.
        if module is not probe_pick:
            assert "software_sic" not in source, module.__name__
        assert "62012" not in source, module.__name__     # no baked SIC codes
        assert "it-jobs" not in source, module.__name__   # no baked category
