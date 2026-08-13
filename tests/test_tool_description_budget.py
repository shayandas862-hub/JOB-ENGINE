"""What the tool descriptions COST, pinned so it can only go down.

Phase 9.5 task 7. Every description in this server is sent to every client on
every turn, so their combined length is rent the owner pays per message,
forever, whether or not the tool is ever called. It had never been measured
in a way anything could enforce: the number lived in a plan file, was
correct on the day it was written, and drifted upward with each phase as
tools were added and wording grew.

So it is a ratchet, in the same spirit as
`tests/test_bug_log_guard_ratchet.py`. It does not judge whether a
description is *good* — that is what the four-label contract and the
wording pins are for. It measures the bill and refuses to let it grow
quietly. Adding a tool is allowed; paying for it is a deliberate edit to a
number, with a reason written beside it.

The honest weakness, stated because this file is about honesty: a budget
measured in characters can be satisfied by making a description SHORTER AND
WORSE. Nothing here can tell the difference. That is why the floor below
exists, why the four-label contract is asserted elsewhere, and why the
wording pins in `tests/test_mcp_door.py` name specific phrases that must
survive — a trim that guts a description fails there rather than passing
here.
"""
from __future__ import annotations

import asyncio
import json


def _tools():
    from mcp_server.server import build_server
    mcp = build_server()

    async def go():
        from fastmcp import Client
        async with Client(mcp) as client:
            return await client.list_tools()
    return asyncio.run(go())


def _description_chars(tools) -> int:
    return sum(len(t.description or "") for t in tools)


# Measured 2026-08-12 at the start of Phase 9.5 task 7: 51 tools, 23,087
# characters of description — roughly 5.8k tokens per turn before a single
# input schema is counted. MAY ONLY GO DOWN, except by a deliberate edit here
# with the reason stated, exactly like the guardless ratchet.
#
# The trim pass then brought it to 20,151 — measured, not estimated — across
# all 51 tools: -2,936 characters, 12.7%, while the toolset GREW by four
# (describe_the_owner, amend_cv_block, record_experience,
# skills_closest_to_closing). The bill fell while the surface grew, which was
# the point of the task.
#
# This number was first written as 19,000 before the trim was done, on nothing
# but hope, and the comment beside it claimed a pass that had not run yet. That
# is the drift this file exists to catch, so it is recorded rather than quietly
# corrected: 19,000 was never measured and is not reachable without gutting
# descriptions. What stopped the trim here was the floor below and the
# four-label contract — every remaining sentence carries something a client
# needs to choose correctly (that a minted key is shown ONCE, that the budget
# resets at midnight UTC, that held_for_retry keeps the claim). Cutting past
# this point removes signal, not wording, and the test that would catch that
# is the one immediately after this constant.
MAX_DESCRIPTION_CHARS = 20_151

#: A description this short cannot be carrying What/When/Returns/Next with
#: anything useful in them. The budget above can be met by gutting
#: descriptions; this is the floor that makes that fail instead.
MIN_DESCRIPTION_CHARS = 120


def test_the_descriptions_every_client_pays_for_never_grow():
    tools = _tools()
    total = _description_chars(tools)
    assert total <= MAX_DESCRIPTION_CHARS, (
        f"tool descriptions now cost {total} characters (~{total // 4} tokens) "
        f"per client turn, up from the pinned {MAX_DESCRIPTION_CHARS}. Tighten "
        "wording, or raise this number deliberately with the reason — but do "
        "not let the rent drift."
    )


def test_no_description_was_gutted_to_meet_the_budget():
    # The countermeasure to the test above. A budget in characters is happy to
    # be met by deleting meaning, and a tool whose description says nothing is
    # worse than an expensive one — the client cannot choose it correctly and
    # calls the wrong thing, or asks the owner.
    tools = _tools()
    thin = sorted(t.name for t in tools
                  if len(t.description or "") < MIN_DESCRIPTION_CHARS)
    assert thin == [], (
        f"these descriptions are under {MIN_DESCRIPTION_CHARS} characters and "
        f"cannot be carrying their four labels usefully: {thin}")


def test_the_measurement_is_reading_real_descriptions():
    # A control. Every assertion above passes if the server serves no tools,
    # or if the protocol stopped delivering descriptions at all — both of
    # which would read as a spectacularly cheap toolset.
    tools = _tools()
    assert len(tools) >= 50, f"only {len(tools)} tools served — the measurement broke"
    assert _description_chars(tools) > 5_000, \
        "descriptions came back nearly empty — the protocol is not delivering them"


def test_the_input_schemas_are_reported_alongside_so_the_bill_is_honest():
    # Descriptions are not the whole rent: the input schemas ship on every
    # turn too. They are not budgeted here because their size is driven by
    # parameter COUNT rather than by wording, and trimming a parameter is a
    # contract change rather than an edit. But a bill that names only the half
    # someone chose to measure is the kind of number this project distrusts,
    # so the total is asserted to be knowable and stays visible in the failure.
    tools = _tools()
    schemas = sum(len(json.dumps(t.inputSchema or {})) for t in tools)
    total = _description_chars(tools) + schemas
    assert schemas > 0, "no input schemas served — the measurement broke"
    assert total < 40_000, (
        f"descriptions plus input schemas now cost {total} characters "
        f"(~{total // 4} tokens) per turn — descriptions "
        f"{_description_chars(tools)}, schemas {schemas}")
