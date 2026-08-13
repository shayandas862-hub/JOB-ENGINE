"""Lens tools — the universal layer's surface (U2 + U3).

A user's words become rows and answers, never code edits: find_industry_codes
turns "care homes" into ranked SIC candidates (the client AI confirms with
the owner, then writes them with the EXISTING set_promotion_rule); add_skill
records owner-scoped skills with evidence and learned_at; search_sponsors
browses the whole census by plain-English industry / town / board status;
search_hiring answers "who is hiring these words and can sponsor?". Thin
skins over src/criteria, src/discover and src/analysis — zero engine logic
here.
"""
from __future__ import annotations

from fastmcp import FastMCP

from analysis.search import search_hiring as _search_hiring
from audit import record as _audit
from criteria.lens import find_industry_codes as _find_codes
from criteria.writer import add_skill as _add_skill
from discover.census_queries import search_sponsors as _search_sponsors
from mcp_server.annotations import READ, writes
from mcp_server.contract import with_next
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn


def register(mcp: FastMCP) -> None:
    """Hang the two lens tools on the server."""

    @mcp.tool(annotations=READ)
    def find_industry_codes(words: str, limit: int = 12) -> dict:
        """What: translate plain industry words ('care homes', 'restaurants')
        into ranked UK SIC code candidates — each with its official
        description, how many licensed sponsors carry it, and which words
        matched. Deterministic; nothing is written.
        When: setting or widening the owner's industry lens.
        Returns: {candidates: [{code, description, sponsors, matched}]}.
        Next: confirm the codes with the owner, then
        set_promotion_rule(industry_codes=[...])."""
        with get_conn() as conn, conn.cursor() as cur:
            candidates = _find_codes(cur, words, limit=limit)
        if candidates:
            return with_next(
                {"candidates": candidates},
                state=f"{len(candidates)} candidate codes",
                call="set_promotion_rule",
                why="write the codes the owner confirms into the nightly rule")
        return with_next(
            {"candidates": []}, state="no code matched those words",
            call="find_industry_codes",
            why="try different words for the same industry")

    @mcp.tool(annotations=writes(idempotent=True))
    def add_skill(skill: str, level: str | None = None,
                  evidence: str | None = None,
                  learned_at: str | None = None,
                  category: str | None = None) -> dict:
        """What: record one skill on the owner's profile — upserted by
        normalised name, so re-adding updates in place and revives a retired
        skill. evidence (where it was used) and learned_at (ISO date) feed the
        learning-curve ranking; give them whenever known.
        When: the owner names a skill they hold that the profile lacks.
        Returns: {skill, skill_norm, outcome: added|updated}.
        Next: get_skill_gaps to see how the gap list changes."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _add_skill(cur, _owner(cur), skill, level=level,
                                evidence=evidence, learned_at=learned_at,
                                category=category, source="mcp")
            _audit(cur, "add_skill",
                   {"skill": skill, "level": level, "learned_at": learned_at,
                    "category": category},
                   {"outcome": result["outcome"]})
        return with_next(result, state=f"skill {result['outcome']}",
                         call="get_skill_gaps",
                         why="see how the gap list changes with it")

    @mcp.tool(annotations=READ)
    def search_sponsors(industry_words: str | None = None,
                        town: str | None = None,
                        with_boards_only: bool = False,
                        limit: int = 25) -> dict:
        """What: search ALL licensed sponsors by plain-English industry words,
        town, and board status — every row carries its receipts (descriptions
        that matched, board outcome, jobs seen). Any industry.
        When: exploring who can sponsor in an industry or place — e.g.
        "care-home sponsors in Leeds with live boards".
        Returns: {sponsors: [...]} — read-only, never a token.
        Next: promote_company(org_name_norm) to start fetching one."""
        with get_conn() as conn, conn.cursor() as cur:
            rows = _search_sponsors(cur, industry_words, town,
                                    with_boards_only=with_boards_only,
                                    limit=limit)
        if rows:
            return with_next(
                {"sponsors": rows}, state=f"{len(rows)} sponsors",
                call="promote_company",
                why="start fetching one that has a live board")
        return with_next(
            {"sponsors": []}, state="no sponsor matched",
            call="find_industry_codes",
            why="translate the words into codes and check the lens instead")

    @mcp.tool(annotations=READ)
    def search_hiring(role_words: str, town: str | None = None,
                      limit: int = 25) -> dict:
        """What: who is hiring these role words and can sponsor — live tracked
        listings first (apply-able today), then census sightings (titles seen
        while door-knocking; every census org is on the register). The
        matching title is each row's receipt.
        When: answering "who hires care assistants in Leeds?", any industry.
        Returns: {jobs: [{title, company_name, location, source, ...}]}.
        Next: get_job(role_id) for a tracked hit; promote_company for a census
        org worth fetching."""
        with get_conn() as conn, conn.cursor() as cur:
            rows = _search_hiring(cur, role_words, town, limit=limit)
        tracked = sum(1 for r in rows if r.get("source") == "tracked")
        if rows:
            return with_next(
                {"jobs": rows},
                state=f"{len(rows)} hits ({tracked} tracked)",
                call="get_job",
                why="open a tracked hit; census hits can be promoted")
        return with_next(
            {"jobs": []}, state="nobody matched those words",
            call="search_sponsors",
            why="look for sponsors by industry instead")
