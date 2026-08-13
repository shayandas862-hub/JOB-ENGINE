"""The six read tools, driven through the real in-process MCP client.

Every assertion goes over the MCP protocol (fastmcp.Client), never around it.
The DB is mocked (``get_conn`` -> a FakeCursor), so these are fully offline: they
prove each tool is registered, wraps the right engine query, serialises real
psycopg types (date/Decimal/jsonb), and never leaks a secret.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn


def _run(coro):
    return asyncio.run(coro)


# The owner these tools resolve to. A sentinel rather than a realistic id, so
# that finding it in a query's parameters proves the tool passed the owner the
# door resolved — not that some plausible uuid happened to be there.
CALLER = "cccccccc-cccc-4ccc-accc-cccccccccccc"


def _server(monkeypatch, cur: FakeCursor, owner: str = CALLER):
    """Build the production server with the DB layer mocked to `cur`.

    Owner resolution itself is proven in tests/test_mcp_identity.py; here it is
    pinned to `owner` so each tool can be checked for passing that owner down
    into its engine query (Phase 9 task 1b).
    """
    from mcp_server import read_tools
    from mcp_server.server import build_server
    monkeypatch.setattr(read_tools, "get_conn", lambda: fake_conn(cur))
    monkeypatch.setattr(read_tools, "_owner", lambda cur: owner)
    return build_server()


def _owner_params(cur, marker: str):
    """The parameters of the one executed query matching `marker`."""
    return next(p for s, p in cur.executed if marker in s.lower())


READ_TOOLS = {
    "get_apply_queue", "get_job", "get_job_history",
    "get_skill_gaps", "get_run_report", "get_criteria",
    # pipeline-vision additions: census software lot + per-job gap
    "list_software_companies", "get_job_gap",
}


def test_list_software_companies_routes_to_the_census_query(monkeypatch):
    from tests.test_criteria import RoutingCursor
    card = {"org_name_norm": "acme software ltd",
            "organisation_name": "Acme Software Ltd",
            "probe_outcome": "board_found"}
    cur = RoutingCursor([("from sponsor_census", [card])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("list_software_companies",
                                       {"limit": 5, "with_boards_only": True})
            assert r.structured_content["result"][0]["org_name_norm"] == "acme software ltd"
            sql, params = cur.executed[0]
            assert "industry_codes && %(sic)s::text[]" in sql
            assert "ats_token" not in sql              # never leaks the token
            assert params["n"] == 5
            assert not any("mcp_audit" in s for s, _ in cur.executed)
    _run(go())


def test_get_job_gap_routes_to_the_per_job_gap(monkeypatch):
    from tests.test_criteria import RoutingCursor
    cur = RoutingCursor([
        ("from role_listings", [{"role_id": 42, "role_title": "AI Engineer",
                                 "company_name": "Acme"}]),
        ("from role_skills", [{"skill_asked": "Python", "skill_norm": "python",
                               "skill_type": "must", "i_have_it": True,
                               "my_level": "strong"}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_job_gap", {"role_id": 42})
            assert r.structured_content["result"]["coverage"] == 1.0
            assert r.structured_content["result"]["skills_missing"] == []
    _run(go())


def test_all_six_read_tools_are_registered_on_the_production_server(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
            assert READ_TOOLS <= names
    _run(go())


def test_get_apply_queue_returns_the_ranked_rows_and_serialises_real_types(monkeypatch):
    rows = [{"role_id": 917, "company_name": "Acme", "fit_rank": "High",
             "sponsor_signal": "role-confirmed", "salary_wall": "clears",
             "salary_max": Decimal("54700"), "last_changed_at": datetime(2026, 7, 10, 9, 0),
             "deadline": date(2026, 7, 19)}]
    mcp = _server(monkeypatch, FakeCursor(rows=rows))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_apply_queue", {"limit": 5})
            assert r.is_error is False
            assert r.structured_content["result"][0]["role_id"] == 917
            assert r.structured_content["result"][0]["salary_max"] == "54700"                 # Decimal -> string
            assert r.structured_content["result"][0]["deadline"] == "2026-07-19"              # date -> ISO string
            assert r.structured_content["result"][0]["last_changed_at"] == "2026-07-10T09:00:00"
    _run(go())


def test_get_apply_queue_exposes_a_limit_parameter(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            tool = next(t for t in await client.list_tools() if t.name == "get_apply_queue")
            assert "limit" in tool.inputSchema.get("properties", {})
    _run(go())


def test_get_skill_gaps_returns_missing_skills(monkeypatch):
    rows = [{"skill": "Kubernetes", "skill_type": "tool", "demand": 12, "my_level": None}]
    mcp = _server(monkeypatch, FakeCursor(rows=rows))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_skill_gaps", {"limit": 10})
            assert r.structured_content["result"] == rows
    _run(go())


def test_get_skill_gaps_with_role_words_uses_the_words_search(monkeypatch):
    # U3: the same tool answers "what do care jobs want that I lack" — the
    # optional role_words switch routes to the words-scoped gap search
    # instead of the owner's-queue view. No new tool, generalised in place.
    from mcp_server import read_tools
    called = {}
    monkeypatch.setattr(
        read_tools, "_gaps_for_words",
        lambda cur, owner, words, limit: called.update(
            words=words, limit=limit) or [{"skill": "Care Planning",
                                           "demand": 9, "i_have_it": False}])
    mcp = _server(monkeypatch, FakeCursor(rows=[{"profile_id": "p1"}]))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "get_skill_gaps", {"role_words": "care assistant"})
            assert called == {"words": "care assistant", "limit": 20}
            assert r.structured_content["result"][0]["skill"] == "Care Planning"
    _run(go())


def test_get_job_returns_the_record_and_never_a_secret(monkeypatch):
    rows = [{"role_id": 917, "company_name": "Acme", "role_title": "AI Engineer",
             "role_url": "https://x/y", "jd_full": "…", "role_status": "open"}]
    mcp = _server(monkeypatch, FakeCursor(rows=rows))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_job", {"role_id": 917})
            assert r.structured_content["result"]["role_id"] == 917
            assert "ats_token" not in r.structured_content["result"]                          # secret never present
    _run(go())


def test_get_job_returns_null_when_the_role_is_unknown(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_job", {"role_id": 999})
            assert r.structured_content["result"] is None
    _run(go())


def test_get_job_history_returns_the_events(monkeypatch):
    rows = [{"event_id": 5, "event_type": "changed", "occurred_at": "2026-07-10T09:00:00",
             "changes": {"salary_text": {"old": "£50k", "new": "£55k"}}, "run_id": 3}]
    mcp = _server(monkeypatch, FakeCursor(rows=rows))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_job_history", {"role_id": 917})
            assert r.structured_content["result"][0]["event_type"] == "changed"
            assert r.structured_content["result"][0]["changes"]["salary_text"]["new"] == "£55k"   # jsonb preserved
    _run(go())


def test_get_run_report_reads_the_latest_run_when_no_id_is_given(monkeypatch):
    rows = [{"run_id": 7, "status": "ok", "started_at": "…",
             "finished_at": "…", "stages": [{"name": "fetch", "ok": True}]}]
    cur = FakeCursor(rows=rows)
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_run_report", {})
            assert r.structured_content["result"]["run_id"] == 7 and r.structured_content["result"]["status"] == "ok"
            assert "limit 1" in cur.executed[-1][0].lower()           # latest, not a specific id
    _run(go())


def test_get_run_report_reads_a_specific_run_by_id(monkeypatch):
    cur = FakeCursor(rows=[{"run_id": 3, "status": "failed", "stages": []}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_run_report", {"run_id": 3})
            assert r.structured_content["result"]["run_id"] == 3
            assert cur.executed[-1][1] == (3,)                        # queried by id
    _run(go())


def test_get_criteria_returns_criteria_and_never_a_secret(monkeypatch):
    from criteria.loader import Criteria
    from mcp_server import read_tools
    canned = Criteria(profile_id="p1", name="Owner", salary_floor=45000.0,
                      threshold_standard=48000.0, threshold_new_entrant=38000.0,
                      kill_keywords=["clearance"], role_patterns=["AI Engineer"])
    monkeypatch.setattr(read_tools, "load_criteria", lambda cur: canned)
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("get_criteria", {})
            assert r.structured_content["result"]["name"] == "Owner"
            assert r.structured_content["result"]["role_patterns"] == ["AI Engineer"]
            # The Criteria contract carries no profile secrets — pin that it stays that way.
            for secret in ("notification_channel", "notion_token_ref", "contact_email"):
                assert secret not in r.structured_content["result"]
    _run(go())


# ---- the caller's owner reaches the query (Phase 9 task 1b) ---------------

def test_every_owner_scoped_read_tool_passes_the_callers_owner_down(monkeypatch):
    # Task 1a resolved WHO is calling; this is the half that spends the
    # answer. Each tool is driven over the real MCP protocol and the sentinel
    # owner is looked for in the parameters the engine query actually
    # received — not in the SQL text, which could name owner_id while binding
    # somebody else's. get_job_gap is checked in both of its queries because
    # it asks two separate owner-sensitive questions.
    from tests.test_criteria import RoutingCursor
    cur = RoutingCursor([
        ("from v_apply_queue", [{"role_id": 917}]),
        ("from v_skill_gap", [{"skill": "K8s", "demand": 3}]),
        ("from role_listings", [{"role_id": 42, "role_title": "T",
                                 "company_name": "Acme"}]),
        ("from role_skills", []),
        ("from listing_events", []),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            await client.call_tool("get_apply_queue", {"limit": 5})
            assert _owner_params(cur, "from v_apply_queue") == (CALLER, 5)

            await client.call_tool("get_skill_gaps", {"limit": 10})
            assert _owner_params(cur, "from v_skill_gap") == (CALLER, 10)

            await client.call_tool("get_job", {"role_id": 917})
            assert _owner_params(cur, "from role_listings") == (917, CALLER)

            await client.call_tool("get_job_history", {"role_id": 917})
            assert _owner_params(cur, "from listing_events") == (917, CALLER, 50)

            await client.call_tool("get_job_gap", {"role_id": 42})
            assert _owner_params(cur, "from role_skills") == (CALLER, 42)
    _run(go())
