"""FastMCP server factory + stdio entrypoint.

The server is a registry of thin tool wrappers. Each feature area (read tools,
action tools, review tools) lives in its own module exposing ``register(mcp)``;
``build_server()`` applies them all in order. This module is the composition
root — the one place that knows the full tool set.

Design rules (enforced by review, not just convention):
  * No business logic here or in any tool module. A tool that needs new
    behaviour calls a tested function in ``src/``.
  * ``build_server()`` is pure construction: it reads no secret and opens no
    connection. Tools touch the DB/engine only when actually invoked, so the
    server imports and lists its tools with an empty environment.
"""
from __future__ import annotations

import os
from typing import Callable

from fastmcp import FastMCP

SERVER_NAME = "goal-a-engine"

# The server-level orientation a client reads once, at connect, before it has
# called anything (M2). It answers what 41 tool descriptions cannot: where the
# loop starts, how to find the next step, and which decisions are not the
# client's to make. Every tool named here is checked to exist by
# tests/test_mcp_door.py — a rename that misses this paragraph would hand a
# cold client a dangling pointer as the first thing it reads.
INSTRUCTIONS = """\
A sponsor-aware job-search engine. It runs itself nightly — finding employers
that can legally sponsor, tracking their jobs, and matching them to one
owner's profile with receipts. These tools are how you and the owner work
what it found. The engine calls no AI of its own; the reading and the writing
are yours.

Start every session at daily_brief. Every tool answers in the same envelope —
{"result": ..., "next": {"state", "call", "why"}} — where next.call names the
one tool to run next and why. Follow it until next.call is null, and you will
have run the whole loop without needing prompts of your own.

The usual round: daily_brief, then the reading tray (get_reading_batch, then
submit_reading for each job you read, or skip_reading for a near miss not
worth the owner's time), then any open questions (list_review_flags,
resolve_review_flag), then the queue itself (get_apply_queue, get_job,
serve_cv, submit_cv).

A brand-new owner starts one step earlier: get_intake_interview serves the
versioned interview that builds their fact base. Record every fact as a
draft and let the owner confirm each wording — the interview's rules ride
with the prompt.

Three rules this server enforces, so expect them rather than work around
them:
  * The human applies. Nothing here submits an application; mark_applied only
    records that the owner already did.
  * You propose, the owner decides. add_cv_block always writes a draft, and
    only confirm_cv_block — after the owner approves the exact wording — makes
    a fact usable in a CV.
  * Claims are checked, not trusted. What you extract and what you write are
    traced against the stored text; anything ungrounded is dropped or replaced
    by the verbatim fact, and the result tells you which.

Every number this engine gives you carries its receipts. Pass them on to the
owner rather than the number alone — including the uncomfortable ones, like
how little of their industry has been reached so far.
"""

# A registrar hangs one or more tools on the server: ``register(mcp) -> None``.
Registrar = Callable[[FastMCP], None]


def _default_registrars() -> list[Registrar]:
    """The production registrars, in the order tools should be applied.

    Imported lazily so build_server stays a cheap, import-light call: read
    tools, action tools, review tools, census tools, contract-v2 loop tools,
    lens tools.
    """
    from mcp_server.action_tools import register as register_action
    from mcp_server.census_tools import register as register_census
    from mcp_server.cv_tools import register as register_cv
    from mcp_server.key_tools import register as register_keys
    from mcp_server.lens_tools import register as register_lens
    from mcp_server.loop_tools import register as register_loop
    from mcp_server.onboarding_tools import register as register_onboarding
    from mcp_server.read_tools import register as register_read
    from mcp_server.review_tools import register as register_review
    return [register_read, register_action, register_review, register_census,
            register_loop, register_lens, register_cv, register_onboarding,
            register_keys]


def build_server(registrars: list[Registrar] | None = None, *,
                 auth=None, middleware=None) -> FastMCP:
    """Construct the FastMCP server and apply every tool registrar.

    Pure construction — no secret is read and no connection is opened here.
    ``registrars`` is an injection seam for tests; production uses
    :func:`_default_registrars`. ``auth``/``middleware`` are transport
    config passed straight to FastMCP (the HTTP door's token gate and rate
    limiter, built in mcp_server.transport) — never logic. INSTRUCTIONS rides
    along on every build, injected registrars included: a test server is a
    cold client's server too.
    """
    kwargs = {}
    if auth is not None:
        kwargs["auth"] = auth
    if middleware is not None:
        kwargs["middleware"] = middleware
    mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS, **kwargs)
    for register in (_default_registrars() if registrars is None else registrars):
        register(mcp)
    return mcp


def main() -> None:
    """Entrypoint. MCP_TRANSPORT=http serves the hosted door (token-gated,
    rate-limited, Cloud Run shaped); default is stdio for Claude Code/Desktop."""
    if os.environ.get("MCP_TRANSPORT", "").strip().lower() == "http":
        from mcp_server.transport import http_settings
        settings = http_settings()
        build_server(auth=settings["auth"],
                     middleware=settings["middleware"]).run(
            transport="http", host=settings["host"], port=settings["port"])
        return
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
