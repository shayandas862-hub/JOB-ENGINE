"""Tests for the FastMCP server scaffold — construction, the tool-registry
pattern, and the stdio entrypoint.

The server is a *skin*: it holds no business logic. These tests drive it through
the real in-process MCP client (``fastmcp.Client``), so every assertion goes over
the actual protocol, not around it. Fully offline — no subprocess, no DB, no
network.
"""
from __future__ import annotations

import asyncio

from fastmcp import Client, FastMCP


def _run(coro):
    """Drive an async coroutine to completion from a sync test (no pytest-asyncio)."""
    return asyncio.run(coro)


def test_build_server_returns_a_named_fastmcp_that_serves_its_tools():
    # Arrange / Act
    from mcp_server.server import SERVER_NAME, build_server
    mcp = build_server()

    # Assert — a real FastMCP, named, serving its production tools over the
    # protocol. (The specific tool set is pinned per feature in its own test.)
    assert isinstance(mcp, FastMCP)
    assert mcp.name == SERVER_NAME

    async def go():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert isinstance(tools, list) and len(tools) > 0
    _run(go())


def test_build_server_opens_no_connection_and_reads_no_secret():
    # Constructing the server must be pure: no DATABASE_URL/GEMINI_API_KEY read,
    # no DB connection. It builds fine with the environment stripped bare.
    import os
    from unittest import mock

    from mcp_server.server import build_server
    with mock.patch.dict(os.environ, {}, clear=True):
        mcp = build_server()  # must not raise
    assert isinstance(mcp, FastMCP)


def test_registry_applies_registrars_and_serves_their_tools_over_the_protocol():
    # The registry pattern: a registrar is register(mcp) -> None that hangs one or
    # more thin tool wrappers on the server. build_server applies every registrar,
    # in order. We inject a fake registrar and confirm the tool is discoverable and
    # callable through the MCP client — proving the pattern end-to-end.
    from mcp_server.server import build_server

    def register_probe(mcp: FastMCP) -> None:
        @mcp.tool
        def probe(x: int) -> dict:
            """Double a number (test-only probe wrapper)."""
            return {"doubled": x * 2}

    mcp = build_server(registrars=[register_probe])

    async def go():
        async with Client(mcp) as client:
            names = [t.name for t in await client.list_tools()]
            assert names == ["probe"]
            result = await client.call_tool("probe", {"x": 21})
            assert result.is_error is False
            assert result.data == {"doubled": 42}
    _run(go())


def test_registrars_are_applied_in_order():
    from mcp_server.server import build_server
    order: list[str] = []
    mcp = build_server(registrars=[
        lambda _m: order.append("first"),
        lambda _m: order.append("second"),
    ])
    assert isinstance(mcp, FastMCP)
    assert order == ["first", "second"]


def test_default_registrars_are_wired_in_from_the_composition_root():
    # build_server() with no override uses the production registrar list. It is a
    # list of callables (empty until the read tools land in the next task); the
    # point is that the seam exists and is honoured.
    from mcp_server.server import _default_registrars
    registrars = _default_registrars()
    assert isinstance(registrars, list)
    assert all(callable(r) for r in registrars)


def test_main_serves_over_stdio(monkeypatch):
    # main() must serve over stdio and nothing else. We stub build_server so the
    # test never starts a blocking server; we only assert the transport wiring.
    from mcp_server import server

    captured: dict = {}

    class FakeServer:
        def run(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server, "build_server", lambda: FakeServer())
    server.main()
    assert captured == {"transport": "stdio"}


PHASE5_TOOLS = {
    # read (6)
    "get_apply_queue", "get_job", "get_job_history",
    "get_skill_gaps", "get_run_report", "get_criteria",
    # Phase 9.5 task 4: the same gap data ranked by EFFORT rather than by
    # demand — what is one sentence away from being usable on a CV.
    "skills_closest_to_closing",
    # action (7) — Stage C split run_pipeline into preview_pipeline (sync,
    # seconds) + start_pipeline (detached, ~12 min), because a blocking run
    # behind Cloud Run's 300s request timeout is a guaranteed 504.
    "mark_applied", "snooze_listing", "set_criteria",
    "add_target_company", "preview_pipeline", "start_pipeline",
    "send_test_nudge",
    # review (2)
    "list_review_flags", "resolve_review_flag",
}

# The pipeline-vision bridge: census software lot, per-job gap, promotion.
BRIDGE_TOOLS = {"list_software_companies", "get_job_gap", "promote_company"}

# Phase 6 adds the discovery action tools (thin wrappers over src/discover).
DISCOVERY_TOOLS = {"discover_company", "classify_from_url"}
# Phase 7 adds the CV maker tool (thin wrapper over src/cv); Phase 8.5
# task 0 (U8) adds the serve-all pair — the client AI selects from EVERY
# confirmed fact, the truth gate stays the ceiling, the engine renders.
CV_TOOLS = {"generate_cv", "serve_cv", "submit_cv",
            "add_cv_block", "list_cv_blocks", "confirm_cv_block",
            "retire_cv_block",
            # Phase 9.5 task 1: the same fact base read back as understanding
            # rather than as rows — what can be proven, and what cannot.
            "describe_the_owner",
            # M6 (Phase 9.5 task 2): retire-plus-redraft in one
            # audited step, still never an in-place mutation.
            "amend_cv_block"}
# Phase 7.5 adds the census sweep switches (detached trigger + scoreboard);
# the pipeline-vision work adds Pass-1 switches (run_classification +
# classify_status).
CENSUS_TOOLS = {"run_sweep", "sweep_status", "run_classification",
                "classify_status"}
# Phase 7.8 contract v2: the loop any vendor's AI runs with zero client-side
# prompting — the agenda, the reading tray trio (skip_reading joined in
# Phase 8.5 / U7 for the near-miss tier), and the promotion rule pair.
LOOP_TOOLS = {"daily_brief", "get_reading_batch", "submit_reading",
              "skip_reading", "get_promotion_rule", "set_promotion_rule"}
# Phase 8.5 / U2+U3: the lens pair (words→codes translator + skills entry)
# and the universal searches (any-industry sponsors, who-is-hiring).
LENS_TOOLS = {"find_industry_codes", "add_skill", "search_sponsors",
              "search_hiring"}
# Phase 9 task 4: onboarding — the served intake-v1 interview (0013 §6 M1),
# the operator's profile-creation door, and the owner's own setters (the
# channel is a secret and never echoes; the Notion ref is a pointer, never
# a token).
ONBOARDING_TOOLS = {"get_intake_interview", "create_profile",
                    "set_notification_channel", "set_notion_token_ref",
                    # M7 (Phase 9.5 task 3): the interview's own writer — one
                    # experience becomes a fact AND the skills it evidences,
                    # joined, because the prompt telling clients to make two
                    # calls demonstrably did not keep the vocabularies in step.
                    "record_experience"}

# Phase 9 task 6: the stranger tier's own two. A signed-in owner mints and
# revokes their OWN keys, which is what takes the founder out of the loop for
# somebody he has never met. Refused for every other kind of caller —
# tests/test_self_serve_keys.py is where that is proven.
KEY_TOOLS = {"issue_my_key", "revoke_my_key"}


def test_server_exposes_the_full_toolset_each_with_a_description():
    # Contract: exactly the Phase 5 tools plus discovery + CV + census +
    # bridge + contract-v2 loop + lens + onboarding + self-serve key tools
    # (47 since task 6's pair joined), and every one carries a description +
    # input schema (a client AI relies on the description to choose a tool).
    from mcp_server.server import build_server
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert ({t.name for t in tools}
                    == PHASE5_TOOLS | DISCOVERY_TOOLS | CV_TOOLS | CENSUS_TOOLS
                    | BRIDGE_TOOLS | LOOP_TOOLS | LENS_TOOLS
                    | ONBOARDING_TOOLS | KEY_TOOLS)
            for t in tools:
                assert t.description and t.description.strip(), f"{t.name}: no description"
                assert isinstance(t.inputSchema, dict)
    _run(go())


def test_contract_v2_every_description_reads_what_when_returns_next():
    # The what/when/returns/what-next contract (decision 2026-08-02): a client
    # AI must be able to run the whole loop from descriptions alone.
    from mcp_server.server import build_server
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            for t in await client.list_tools():
                for label in ("What:", "When:", "Returns:", "Next:"):
                    assert label in (t.description or ""), \
                        f"{t.name}: description missing '{label}'"
    _run(go())


def test_contract_v2_next_block_is_one_shape_everywhere():
    # The uniform envelope helper the tool modules share: {result, next} with
    # next = {state, call, why}. One shape, enforced at the one place it is
    # built.
    from mcp_server.contract import with_next
    out = with_next([1, 2], state="2 rows", call="get_job",
                    why="read one listing")
    assert out == {"result": [1, 2],
                   "next": {"state": "2 rows", "call": "get_job",
                            "why": "read one listing"}}
    terminal = with_next({}, state="done", call=None, why="nothing left")
    assert terminal["next"]["call"] is None


def test_every_next_hint_names_a_tool_that_actually_exists():
    # next.call is the machine-readable half of contract v2 — it is what a
    # client AI follows to take its next step. A tool rename that misses a
    # hint leaves a dangling pointer: the client calls a tool that is not
    # there, and NO other test notices. Stage C's run_pipeline split moved
    # eight of these at once, which is exactly when this goes wrong.
    import pathlib
    import re
    from mcp_server.server import build_server
    root = pathlib.Path(__file__).resolve().parents[1]
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            return {t.name for t in await client.list_tools()}
    names = _run(go())

    dangling, checked = [], 0
    for path in sorted((root / "src" / "mcp_server").rglob("*.py")):
        text = path.read_text()
        # Tokens a docstring documents inside {...} are RETURNED FIELDS, not
        # tools (e.g. "Returns: {role_id, jd_full}"), so prose naming them is
        # naming data. Discriminating on the doc itself beats an allowlist.
        fields = set(re.findall(r"\b([a-z]+_[a-z_]+)\b",
                                " ".join(re.findall(r"\{([^}]*)\}", text))))
        # the with_next(call=...) kwarg — the contract field itself
        hints = [(m, "call=") for m in re.findall(r'call="([a-z_]+)"', text)]
        # and the "Next: <tool>" prose a client reads from the description
        # (parenthesised args stripped so mark_applied(role_id) checks the tool)
        for line in re.findall(r"Next: (.+)", text):
            hints += [(m, "Next:") for m in
                      re.findall(r"\b([a-z]+_[a-z_]+)\b", re.sub(r"\([^)]*\)", "", line))
                      if m not in fields]
        for target, where in hints:
            checked += 1
            if target not in names:
                dangling.append(f"{path.name} [{where}] -> {target}")

    assert checked > 30, f"the scan found almost nothing ({checked}) — it is broken"
    assert dangling == [], f"next hints point at non-existent tools: {dangling}"


def test_the_engine_never_imports_the_mcp_server():
    # Done-looks-like: killing the MCP server changes nothing about the daily
    # loop. Prove the scheduled run path is wholly independent — no engine file (any
    # script, or any src module outside mcp_server) references the MCP skin.
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    engine = list((root / "scripts").glob("*.py"))
    engine += [p for p in (root / "src").rglob("*.py") if "mcp_server" not in p.parts]
    offenders = [str(p.relative_to(root)) for p in engine if "mcp_server" in p.read_text()]
    assert offenders == [], f"engine files reference the MCP server: {offenders}"
