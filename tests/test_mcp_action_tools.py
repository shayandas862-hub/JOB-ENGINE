"""The six action tools, driven through the real in-process MCP client.

The DB (get_conn), the pipeline trigger (subprocess), and the push client are all
mocked, so these are fully offline: nothing is written, no pipeline is spawned,
no nudge is sent. We assert each tool wraps the right engine write and never
returns a secret.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor


def _run(coro):
    return asyncio.run(coro)


# The owner these tools resolve to. A sentinel rather than a realistic id, so
# that finding it in a query's parameters proves the tool passed the owner the
# door resolved — not that some plausible uuid happened to be there.
CALLER = "cccccccc-cccc-4ccc-accc-cccccccccccc"


def _server(monkeypatch, cur=None, owner: str = CALLER):
    """Production server with action_tools' DB layer mocked to `cur`.

    Owner resolution itself is proven in tests/test_mcp_identity.py; here it is
    pinned to `owner` so each write can be checked for acting as that owner and
    nobody else (Phase 9 task 1b).
    """
    from mcp_server import action_tools
    from mcp_server.server import build_server
    if cur is not None:
        monkeypatch.setattr(action_tools, "get_conn", lambda: fake_conn(cur))
    monkeypatch.setattr(action_tools, "_owner", lambda cur: owner)
    return build_server()


ACTION_TOOLS = {
    "mark_applied", "snooze_listing", "set_criteria",
    "add_target_company", "send_test_nudge",
    # Stage C: run_pipeline split — a preview waits (seconds), a real run
    # detaches (~12 min, would 504 behind Cloud Run's 300s timeout).
    "preview_pipeline", "start_pipeline",
    # pipeline-vision addition: the census→pipeline bridge
    "promote_company",
}


def test_promote_company_bridges_the_census_to_the_fetch_list(monkeypatch):
    card = {"org_name_norm": "acme software ltd", "sponsor_id": 7,
            "organisation_name": "Acme Software Ltd", "town_city": "London",
            "probe_outcome": "board_found", "ats_type": "greenhouse",
            "ats_token": "acme", "careers_url": "https://x",
            "local_jobs_seen": 4}
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from sponsor_census", [card]),
        ("from target_companies", []),
        ("insert into target_companies", [{"company_id": 9}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("promote_company",
                                       {"org_name_norm": "acme software ltd"})
            assert r.data["result"]["outcome"] == "promoted" and r.data["result"]["company_id"] == 9
            assert "acme" not in str({k: v for k, v in r.data["result"].items()
                                      if k == "ats_token"})  # token never returned
            assert any("insert into mcp_audit" in s for s, _ in cur.executed)
    _run(go())


def test_all_six_action_tools_are_registered(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
            assert ACTION_TOOLS <= names
    _run(go())


def test_mark_applied_records_the_application(monkeypatch):
    cur = FakeCursor(rows=[{"role_title": "AI Engineer"}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("mark_applied", {"role_id": 917})
            assert r.data["result"]["applied"] is True
            assert r.data["result"]["role_title"] == "AI Engineer"
            assert any("update role_listings" in e[0].lower() for e in cur.executed)
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_mark_applied_reports_an_unknown_role(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor(rows=[]))

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("mark_applied", {"role_id": 999})
            assert r.data["result"]["applied"] is False
    _run(go())


def test_snooze_listing_suppresses_future_nudges(monkeypatch):
    cur = FakeCursor(rows=[{"role_title": "AI Engineer"}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("snooze_listing", {"role_id": 917})
            assert r.data["result"]["snoozed"] is True
            assert any("nudged_at = now()" in e[0].lower() for e in cur.executed)
    _run(go())


def test_set_criteria_updates_the_owner_constraint(monkeypatch):
    cur = FakeCursor(rows=[{"profile_id": "p-1"}], rowcount=1)
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("set_criteria", {"salary_floor": 45000})
            assert r.data["result"]["updated"] == {"salary_floor": 45000}
            sqls = " ".join(e[0].lower() for e in cur.executed)
            assert "update my_constraints" in sqls
            # the constraint is written against the CALLER, not the first profile
            write = next(e for e in cur.executed
                         if "update my_constraints" in e[0].lower())
            assert CALLER in write[1]
    _run(go())


def test_set_criteria_with_nothing_to_set_touches_nothing(monkeypatch):
    cur = FakeCursor(rows=[{"profile_id": "p-1"}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("set_criteria", {})
            assert r.data["result"]["updated"] == {}
            assert cur.executed == []              # short-circuits before any DB hit
    _run(go())


def test_add_target_company_registers_and_returns_the_id(monkeypatch):
    cur = RoutingCursor([("from profiles", [{"profile_id": "p-1"}]),
                         ("target_companies", [{"company_id": 123}])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("add_target_company", {"company_name": "Acme AI"})
            assert r.data["result"]["company_id"] == 123
            assert r.data["result"]["company_name"] == "Acme AI"
    _run(go())


def test_discover_company_onboards_a_board_and_audits(monkeypatch):
    from discover import company
    from fetch.ats import ATS_GREENHOUSE, Classification
    monkeypatch.setattr(company, "classify_company",
                        lambda name, session=None: Classification(
                            name, ATS_GREENHOUSE, "acme", "https://boards.greenhouse.io/acme", 9))
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "p-1"}]),
        ("from target_companies", []),
        ("licensed_sponsors", [{"sponsor_id": 42, "organisation_name": "Acme",
                                "town_city": "London", "rating": "A",
                                "route": "Skilled Worker", "is_skilled_worker": True}]),
        ("insert into target_companies", [{"company_id": 700}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("discover_company", {"company_name": "Acme"})
            assert r.data["result"]["outcome"] == "onboarded" and r.data["result"]["company_id"] == 700
            assert r.data["result"]["sponsor_verdict"]["in_register"] is True
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_classify_from_url_rejects_an_unrecognized_url_via_the_tool(monkeypatch):
    cur = RoutingCursor([("from profiles", [{"profile_id": "p-1"}])])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "classify_from_url",
                {"company_name": "Beta Co", "careers_url": "https://beta.com/careers"})
            assert r.data["result"]["outcome"] == "unrecognized_url"
            # the action is still audited even when it makes no write
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_generate_cv_tool_wraps_the_regenerator_and_audits(monkeypatch):
    from mcp_server import action_tools
    cur = RoutingCursor([("from profiles", [{"profile_id": "p-1"}])])
    seen = {}
    monkeypatch.setattr(
        action_tools, "_regen_cv",
        lambda c, owner, role_id, emphasis=(): seen.update(
            owner=owner, role_id=role_id, emphasis=emphasis)
        or {"role_id": role_id, "filed": True, "card_url": "https://www.notion.so/x"})
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("generate_cv", {"role_id": 917, "emphasis": "ml, rag"})
            assert r.data["result"]["filed"] is True
            assert seen == {"owner": CALLER, "role_id": 917, "emphasis": ["ml", "rag"]}
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_preview_pipeline_delegates_to_the_preview_and_never_spawns(monkeypatch):
    from mcp_server import action_tools
    cur = FakeCursor()
    monkeypatch.setattr(action_tools, "get_conn", lambda: fake_conn(cur))
    called = {}
    monkeypatch.setattr(
        action_tools, "_preview",
        lambda: called.update(hit=True)
        or {"dry_run": True, "returncode": 0, "summary": "would nudge 5"})
    from mcp_server.server import build_server
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("preview_pipeline", {})
            assert r.data["result"]["dry_run"] is True
            assert r.data["result"]["returncode"] == 0
            assert called["hit"] is True
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_start_pipeline_returns_immediately_and_never_waits(monkeypatch):
    # Hosted behind Cloud Run's 300s timeout, a blocking ~12-minute run is a
    # guaranteed 504. The tool must hand back a log path, not a returncode.
    from mcp_server import action_tools
    cur = FakeCursor()
    monkeypatch.setattr(action_tools, "get_conn", lambda: fake_conn(cur))
    monkeypatch.setattr(action_tools, "_owner", lambda cur: CALLER)
    called = {}
    monkeypatch.setattr(
        action_tools, "_start",
        lambda owner=None: called.update(hit=True, owner=owner)
        or {"started": True, "log_path": "/x/ops/run-logs/run-1.log"})
    from mcp_server.server import build_server
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("start_pipeline", {})
            assert r.data["result"]["started"] is True
            assert "run-logs" in r.data["result"]["log_path"]
            assert "returncode" not in r.data["result"]   # it did NOT wait
            assert called["hit"] is True
            assert called["owner"] == CALLER   # the run is charged to its caller
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_actions_write_a_secret_free_audit_row(monkeypatch):
    cur = FakeCursor(rows=[{"role_title": "AI Engineer"}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            await client.call_tool("mark_applied", {"role_id": 917})
            audit = next(e for e in cur.executed if "insert into mcp_audit" in e[0].lower())
            params = audit[1]
            assert params[0] == "mark_applied"                 # tool name
            assert '"role_id": 917' in params[1]               # arg summary
            assert "applied" in params[2]                      # result summary
    _run(go())


def test_send_test_nudge_without_a_channel_does_not_send(monkeypatch):
    cur = FakeCursor(rows=[{"notification_channel": None}])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("send_test_nudge", {})
            assert r.data["result"] == {"channel_configured": False, "sent": False}
    _run(go())


def test_send_test_nudge_with_a_channel_sends_without_leaking_it(monkeypatch):
    from notify import push
    cur = FakeCursor(rows=[{"notification_channel": "ntfy:secret-topic"}])
    monkeypatch.setattr(push, "send_push", lambda ch, t, b: True)
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("send_test_nudge", {})
            assert r.data["result"] == {"channel_configured": True, "sent": True}
            assert "secret-topic" not in str(r.data["result"])   # channel/topic never returned
            # and it asked for the CALLER's channel, not the first profile's:
            # this is the only tool whose mistake reaches somebody's phone.
            channel_q = next(e for e in cur.executed
                             if "notification_channel" in e[0].lower())
            assert "where profile_id = %s" in channel_q[0].lower()
            assert channel_q[1] == (CALLER,)
    _run(go())
