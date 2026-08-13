"""The MCP door's own contract — server instructions (M2) and tool
annotations (M3), from plans/0013 §6.

Nothing here is about engine behaviour. It is about what a *cold* client AI —
one that has never seen this engine — can work out for itself before it calls
anything: where the loop starts, and which tools are safe to run without
asking the owner first.

Every assertion goes over the real MCP protocol (``fastmcp.Client``), never
around it: an annotation set on a decorator but lost in transport would be
worth nothing. Fully offline — no DB, no network.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import re

from fastmcp import Client

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(coro):
    """Drive an async coroutine to completion from a sync test."""
    return asyncio.run(coro)


def _serve():
    """Everything a cold client sees at connect: instructions + the tools."""
    from mcp_server.server import build_server
    mcp = build_server()

    async def go():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return client.initialize_result.instructions, tools
    return _run(go())


def _tools() -> dict:
    """Tool name -> the tool as the protocol delivers it."""
    return {t.name: t for t in _serve()[1]}


# --- M3 · the classification, pinned ------------------------------------
# The rule each set applies is stated where the set is defined, because the
# rule is the thing under review — the names are just its consequence.

# A read tool writes NOTHING: no row, no stamp, no audit trail, no spawned
# script. These are the tools a client may run without asking the owner.
READ_ONLY = {
    "list_software_companies", "get_job_gap", "get_apply_queue", "get_job",
    "get_job_history", "get_skill_gaps", "get_run_report", "get_criteria",
    "list_review_flags", "sweep_status", "classify_status", "daily_brief",
    "get_promotion_rule", "find_industry_codes", "search_sponsors",
    "search_hiring", "serve_cv", "list_cv_blocks", "get_intake_interview",
    # The mirror (Phase 9.5 task 1). It belongs here in the strongest sense:
    # it stores no opinion of the person, so calling it twice cannot leave a
    # trace of having been called at all — cv.mirror re-forms the answer from
    # the rows every time, and tests/test_cv_mirror.py asserts it issues no
    # write of any kind.
    "describe_the_owner",
    # The learning curve (task 4) — a pure fold over two views and a
    # table, storing nothing and spawning nothing.
    "skills_closest_to_closing",
}

# Reaches outside the database — a fetch, a push, or a detached script that
# does one. preview_pipeline is deliberately NOT here: its dry run makes no
# fetches and sends nothing. set_promotion_rule IS here: a codes change
# starts the door-knock, which goes to the network.
OPEN_WORLD = {
    "discover_company", "classify_from_url", "generate_cv", "start_pipeline",
    "send_test_nudge", "run_sweep", "run_classification", "set_promotion_rule",
}

# Withdraws something the owner cannot restore through this same door.
# Overwriting a value they can simply set back again is not destructive.
DESTRUCTIVE = {"retire_cv_block"}

# Calling again with the same arguments does the thing AGAIN — a second row,
# a second document, a second push, a fresh batch. A client must not blind-
# retry these on a timeout.
NOT_IDEMPOTENT = {
    "add_target_company", "discover_company", "classify_from_url",
    "generate_cv", "start_pipeline", "send_test_nudge", "run_sweep",
    "run_classification", "get_reading_batch", "submit_cv", "add_cv_block",
    "create_profile", "issue_my_key",
    # An amendment writes a NEW draft every time: calling twice
    # leaves two corrections and one retired original, never one
    # correction applied twice. record_experience likewise writes a fresh
    # draft per call (its skills upsert, but the block does not).
    "amend_cv_block", "record_experience",
}


def test_every_tool_declares_whether_it_is_a_read():
    # M3: all 41 shipped with annotations=None, so a client could not tell
    # get_job from mark_applied except by reading prose — which blocks safe
    # auto-approval of reads. readOnlyHint is the flag that unblocks it, and
    # it must be stated explicitly (None is "unknown", not "no").
    tools = _tools()
    # 47 at the Phase 9 close; 48 with task 1's describe_the_owner; 49 with
    # task 2's amend_cv_block; 50 with task 3's record_experience; 51 with
    # task 4's skills_closest_to_closing. Raised deliberately each time —
    # the count is a contract with every client that pays for these
    # descriptions on every turn, so it moves by an edit here and never by a
    # tool quietly appearing.
    assert len(tools) == 51, f"51 tools expected, found {len(tools)}"
    missing = [n for n, t in tools.items()
               if t.annotations is None or t.annotations.readOnlyHint is None]
    assert missing == [], f"no readOnlyHint declared: {sorted(missing)}"


def test_reads_and_writes_are_split_exactly_where_the_rule_says():
    tools = _tools()
    marked = {n for n, t in tools.items() if t.annotations.readOnlyHint}
    assert marked == READ_ONLY, (
        f"wrongly marked read-only: {sorted(marked - READ_ONLY)}; "
        f"read tools not marked: {sorted(READ_ONLY - marked)}")


def test_a_read_only_tool_never_audits_or_spawns():
    # The classification above is a claim; this is the check on it. Every
    # write in this server records an mcp_audit row, and every detached run
    # goes through a _spawn helper — so a tool that calls either is a write,
    # whatever its annotation says. (Partial by construction: a write buried
    # in an engine function it calls is invisible here. It still catches the
    # drift that actually happens — an audit line added to a read tool.)
    writes = {"_audit", "_spawn_detached", "_spawn_knock"}
    offenders = []
    for path in sorted((ROOT / "src" / "mcp_server").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name not in READ_ONLY:
                continue
            called = {c.func.id for c in ast.walk(node)
                      if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            if called & writes:
                offenders.append(f"{path.name}:{node.name} calls {sorted(called & writes)}")
    assert offenders == [], f"marked read-only but writes: {offenders}"


def test_writes_declare_both_hints_that_only_apply_to_them():
    # destructiveHint and idempotentHint are meaningful only when the tool is
    # not read-only (MCP spec). On a write, leaving either unset means the
    # client falls back to the protocol default — destructive=true — and asks
    # the owner about every single call, which is the same uselessness we
    # started with.
    tools = _tools()
    unstated = [n for n, t in tools.items()
                if not t.annotations.readOnlyHint
                and (t.annotations.destructiveHint is None
                     or t.annotations.idempotentHint is None)]
    assert unstated == [], f"write tools missing a hint: {sorted(unstated)}"


def test_only_an_unrecoverable_withdrawal_is_marked_destructive():
    tools = _tools()
    marked = {n for n, t in tools.items()
              if t.annotations.destructiveHint is True}
    assert marked == DESTRUCTIVE, (
        f"over-marked: {sorted(marked - DESTRUCTIVE)}; "
        f"under-marked: {sorted(DESTRUCTIVE - marked)}")


def test_the_tools_that_leave_the_database_say_so():
    tools = _tools()
    marked = {n for n, t in tools.items() if t.annotations.openWorldHint}
    assert marked == OPEN_WORLD, (
        f"wrongly open-world: {sorted(marked - OPEN_WORLD)}; "
        f"reaches out but silent: {sorted(OPEN_WORLD - marked)}")


def test_repeatable_calls_are_told_apart_from_ones_that_double_up():
    tools = _tools()
    marked = {n for n, t in tools.items()
              if not t.annotations.readOnlyHint
              and t.annotations.idempotentHint is False}
    assert marked == NOT_IDEMPOTENT, (
        f"claimed unsafe to repeat: {sorted(marked - NOT_IDEMPOTENT)}; "
        f"claimed safe but repeats its effect: {sorted(NOT_IDEMPOTENT - marked)}")


# --- M2 · the server's own orientation ----------------------------------

def test_a_cold_client_is_given_instructions_at_connect():
    # MCP has a server-level orientation slot; ours was None, so a client
    # that connected knew 41 tool names and nothing about where to start.
    instructions, _ = _serve()
    assert instructions and instructions.strip(), "server serves no instructions"


def test_the_instructions_name_the_entry_point_and_the_envelope():
    # Acceptance (plans/0013 §6 M2): a client that has never seen this engine
    # runs the loop correctly from a standing start. That needs three things
    # said out loud — where to start, how to find the next step, and that the
    # engine never applies for the owner.
    instructions, _ = _serve()
    for needed in ("daily_brief", "next", "call", "mark_applied"):
        assert needed in instructions, f"instructions never mention {needed!r}"


def test_the_instructions_state_who_decides():
    # The two rules a client breaks first if nobody tells it: the human
    # presses apply, and a proposed fact is a draft until the OWNER confirms.
    instructions, _ = _serve()
    assert "confirm_cv_block" in instructions
    assert "draft" in instructions.lower()


def test_every_tool_the_instructions_name_actually_exists():
    # Same failure the next-hint scan guards against, one level up: a tool
    # rename that misses this paragraph leaves a cold client following a
    # pointer to nothing — and the paragraph is the FIRST thing it reads.
    instructions, tools = _serve()
    names = {t.name for t in tools}
    cited = set(re.findall(r"\b([a-z]+_[a-z_]+)\b", instructions))
    assert cited, "the scan found no tool names at all — it is broken"
    assert cited <= names, f"instructions name non-tools: {sorted(cited - names)}"


# --- the fact base's own wording ---------------------------------------

def test_add_cv_block_asks_for_a_life_not_a_career():
    # "career fact" quietly tells a client AI that unpaid work does not
    # count — and transferable evidence from outside paid work is exactly
    # what U8's serve-all design exists to surface. The wording of the one
    # tool that WRITES facts decides what a new user's fact base contains.
    desc = _tools()["add_cv_block"].description or ""
    assert "career fact" not in desc
    assert "life and work" in desc
    assert "outside paid work" in desc
