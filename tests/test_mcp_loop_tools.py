"""The contract-v2 loop tools, driven through the real in-process MCP client.

daily_brief -> get_reading_batch -> submit_reading is the loop any vendor's
AI runs with zero client-side prompting: every result carries the uniform
`next` block (state / call / why) and the reading pair is a pure skin over
src/reading. The rule pair reads and writes the owner's promotion rule.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn


def _run(coro):
    return asyncio.run(coro)


def _server(monkeypatch, cur=None, **stubs):
    from mcp_server import loop_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(loop_tools, "get_conn",
                        lambda: fake_conn(cur or FakeCursor(rows=[])))
    monkeypatch.setattr(loop_tools, "_owner", lambda c: "p1")
    for name, value in stubs.items():
        monkeypatch.setattr(loop_tools, name, value)
    return build_server()


def _next(result):
    data = result.structured_content
    assert set(data.keys()) == {"result", "next"}
    assert set(data["next"].keys()) == {"state", "call", "why"}
    return data["next"]


def test_daily_brief_hands_the_reading_tray_first(monkeypatch):
    brief = {"applications": {"total": 0, "today": 0}, "queue_top": [],
             "to_read": 14, "reviews_open": [], "last_run": None}
    mcp = _server(monkeypatch, assemble_brief=lambda cur, owner: brief)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("daily_brief", {})
            assert r.structured_content["result"] == brief
            nxt = _next(r)
            assert nxt["call"] == "get_reading_batch"
    _run(go())


def test_daily_brief_falls_back_to_the_queue_when_the_tray_is_empty(monkeypatch):
    brief = {"applications": {"total": 3, "today": 0},
             "queue_top": [{"role_id": 1}], "to_read": 0,
             "reviews_open": [], "last_run": None}
    mcp = _server(monkeypatch, assemble_brief=lambda cur, owner: brief)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("daily_brief", {})
            assert _next(r)["call"] == "get_apply_queue"
    _run(go())


def test_get_reading_batch_serves_the_tray_and_points_at_submit(monkeypatch):
    batch = {"prompt_version": "extract-v1", "prompt": "…",
             "required_shape": {}, "claim_minutes": 60,
             "jobs": [{"role_id": 1, "role_title": "DE", "jd_full": "x"}],
             "staged_total": 5}
    mcp = _server(monkeypatch, get_batch=lambda cur, owner, limit: batch)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_reading_batch", {"limit": 5})
            assert r.structured_content["result"]["prompt_version"] == "extract-v1"
            assert _next(r)["call"] == "submit_reading"
    _run(go())


def test_empty_tray_points_back_at_the_brief(monkeypatch):
    batch = {"prompt_version": "extract-v1", "prompt": "…",
             "required_shape": {}, "claim_minutes": 60, "jobs": [],
             "staged_total": 0}
    mcp = _server(monkeypatch, get_batch=lambda cur, owner, limit: batch)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_reading_batch", {})
            assert _next(r)["call"] == "daily_brief"
    _run(go())


def test_submit_reading_is_audited_and_loops_back_for_more(monkeypatch):
    calls = {}

    def fake_accept(cur, owner, role_id, reading, provenance):
        calls["args"] = (owner, role_id, reading, provenance)
        return {"outcome": "accepted", "role_id": role_id,
                "skills_accepted": 2, "rejected_skills": ["Made Up"],
                "salary_rejected": False}
    cur = FakeCursor()
    mcp = _server(monkeypatch, cur=cur, accept_reading=fake_accept)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("submit_reading", {
                "role_id": 7, "reading": {"skills": []},
                "client_label": "claude"})
            assert r.structured_content["result"]["outcome"] == "accepted"
            assert calls["args"][0] == "p1"
            assert calls["args"][3] == "claude"
            assert _next(r)["call"] == "get_reading_batch"
            audits = [s for s, _ in cur.executed if "mcp_audit" in s]
            assert len(audits) == 1
    _run(go())


def test_promotion_rule_roundtrip(monkeypatch):
    rule = {"industry_codes": ["62012"], "min_local_jobs": 1, "auto": True,
            "adzuna_category": "it-jobs"}
    saved = {}

    def fake_save(cur, owner, **kw):
        saved.update(kw)
        return {"owner_id": owner, **rule}
    cur = FakeCursor()
    mcp = _server(monkeypatch, cur=cur,
                  load_rule=lambda c, owner: rule, save_rule=fake_save)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_promotion_rule", {})
            assert r.structured_content["result"] == rule
            assert _next(r)["call"] == "set_promotion_rule"

            r = await client.call_tool("set_promotion_rule",
                                       {"min_local_jobs": 3})
            assert saved == {"industry_codes": None, "min_local_jobs": 3,
                             "auto": None, "adzuna_category": None}
            assert r.structured_content["result"]["min_local_jobs"] == 1   # what the engine stored
            assert _next(r)["call"] == "get_promotion_rule"
    _run(go())


def test_set_promotion_rule_accepts_the_ads_category(monkeypatch):
    # U1: the lens row carries the owner's Adzuna category; the tool passes
    # it through partially like every other field.
    rule = {"industry_codes": ["87300"], "min_local_jobs": 1, "auto": True,
            "adzuna_category": "social-work-jobs"}
    saved = {}

    def fake_save(cur, owner, **kw):
        saved.update(kw)
        return {"owner_id": owner, **rule}
    mcp = _server(monkeypatch, cur=FakeCursor(),
                  load_rule=lambda c, owner: rule, save_rule=fake_save)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "set_promotion_rule", {"adzuna_category": "social-work-jobs"})
            assert saved["adzuna_category"] == "social-work-jobs"
            assert r.structured_content["result"]["adzuna_category"] == "social-work-jobs"
    _run(go())


# ---- U4: knock-on-demand + the honest doors line ---------------------------

def test_new_lens_codes_knock_on_demand(monkeypatch):
    # A fresh lens arrives at ~0.7% door coverage; changing the codes starts
    # the owner-lens sweep DETACHED right away (the sweep lock makes a
    # double-start exit instantly), instead of waiting for someone to run it.
    old = {"industry_codes": ["62012"], "min_local_jobs": 1, "auto": True,
           "adzuna_category": None}
    new = {"industry_codes": ["87300"], "min_local_jobs": 1, "auto": True,
           "adzuna_category": None}
    knocks = []
    mcp = _server(monkeypatch, cur=FakeCursor(),
                  load_rule=lambda c, owner: old,
                  save_rule=lambda c, owner, **kw: {"owner_id": owner, **new},
                  _spawn_knock=lambda owner: knocks.append(owner) or "/logs/knock.log")

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("set_promotion_rule",
                                       {"industry_codes": ["87300"]})
            assert knocks == ["p1"], "the knock was not charged to its owner"
            assert r.structured_content["result"]["knock"] == {"started": True,
                                                 "log_path": "/logs/knock.log"}
            assert r.structured_content["next"]["call"] == "sweep_status"
    _run(go())


def test_unchanged_codes_do_not_knock(monkeypatch):
    # Tweaking the floor (or re-sending the same codes) must NOT start a
    # sweep — the knock fires only when the lens actually changes.
    rule = {"industry_codes": ["62012"], "min_local_jobs": 1, "auto": True,
            "adzuna_category": None}

    def no_knock():
        raise AssertionError("knock must not start when codes are unchanged")
    mcp = _server(monkeypatch, cur=FakeCursor(),
                  load_rule=lambda c, owner: rule,
                  save_rule=lambda c, owner, **kw: {"owner_id": owner, **rule},
                  _spawn_knock=no_knock)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("set_promotion_rule",
                                       {"min_local_jobs": 2})
            assert r.structured_content["result"]["knock"] is None
            r = await client.call_tool("set_promotion_rule",
                                       {"industry_codes": ["62012"]})
            assert r.structured_content["result"]["knock"] is None
    _run(go())


def test_skip_reading_stamps_the_pass_and_audits(monkeypatch):
    # U7: a near-miss the client AI judges irrelevant is SKIPPED — stamped
    # so it never re-stages, audited like every write, honest outcome back.
    cur = FakeCursor()
    mcp = _server(monkeypatch, cur=cur,
                  _skip=lambda c, owner, role_id: {"outcome": "skipped",
                                                   "role_id": role_id})

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("skip_reading", {"role_id": 44})
            assert r.structured_content["result"]["outcome"] == "skipped"
            assert r.structured_content["next"]["call"] == "get_reading_batch"
            assert any("insert into mcp_audit" in s.lower()
                       for s, _ in cur.executed)
    _run(go())


def test_daily_brief_says_the_doors_line_while_coverage_is_low(monkeypatch):
    brief = {"applications": {"total": 0, "today": 0}, "queue_top": [],
             "to_read": 0, "reviews_open": [], "last_run": None,
             "lens_coverage": {"knocked": 43, "total": 6261, "pct": 0.7}}
    mcp = _server(monkeypatch, assemble_brief=lambda c, o: brief)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("daily_brief", {})
            assert r.structured_content["result"]["lens_coverage"]["knocked"] == 43
            # the honest expectation line rides in the state itself
            assert "43/6261" in r.structured_content["next"]["state"]
    _run(go())


def test_daily_brief_stays_quiet_once_the_doors_are_mostly_knocked(monkeypatch):
    brief = {"applications": {"total": 0, "today": 0}, "queue_top": [],
             "to_read": 0, "reviews_open": [], "last_run": None,
             "lens_coverage": {"knocked": 11726, "total": 11931, "pct": 98.3}}
    mcp = _server(monkeypatch, assemble_brief=lambda c, o: brief)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("daily_brief", {})
            assert "doors" not in r.structured_content["next"]["state"]
    _run(go())
