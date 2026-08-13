"""Read tools — the inspection wrappers a client AI uses to see state.

Each tool is a thin skin over ONE existing engine query: it opens a cursor,
calls the query function, and wraps the rows in the contract-v2 envelope
(mcp_server.contract.with_next). No logic lives here — the ranking/wall
logic is in the SQL views, the criteria assembly is in src/criteria. Nothing
here returns a secret (the query functions select curated, secret-free
columns).
"""
from __future__ import annotations

from dataclasses import asdict

from fastmcp import FastMCP

from analysis.curve import closest_to_closing as _closest
from analysis.job_gap import fetch_job_gap
from analysis.search import skill_gaps_for_words as _gaps_for_words
from applyqueue import fetch_job, fetch_queue, fetch_skill_gaps
from criteria.loader import load_criteria
from discover.census_queries import list_software_companies as _software
from history.events import history_for_role
from mcp_server.annotations import READ
from mcp_server.contract import envelope_schema, with_next

# M4 typed result (0013 §6): the queue is rows, each with its receipts.
_QUEUE_RESULT = {"type": "array", "items": {"type": "object"}}
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn
from pipeline.report import latest_run, run_report


def _read(fn, *args):
    """Run a read function against a fresh live cursor and return its result."""
    with get_conn() as conn, conn.cursor() as cur:
        return fn(cur, *args)


def register(mcp: FastMCP) -> None:
    """Hang the read tools on the server."""

    @mcp.tool(annotations=READ)
    def list_software_companies(limit: int = 50,
                                with_boards_only: bool = False) -> dict:
        """What: census software companies, most fetchable first (boards
        found, then most local jobs seen).
        When: hunting companies to promote beyond the nightly rule's picks;
        with_boards_only shows the promotable-today subset.
        Returns: census cards (org_name_norm, probe outcome, jobs seen).
        Next: promote_company(org_name_norm) to start fetching one."""
        rows = _read(lambda cur: _software(cur, limit,
                                           with_boards_only=with_boards_only))
        return with_next(
            rows, state=f"{len(rows)} census companies",
            call="promote_company" if rows else "sweep_status",
            why="promote one onto the fetch list" if rows
            else "no cards match — check the census scoreboard")

    @mcp.tool(annotations=READ)
    def get_job_gap(role_id: int) -> dict:
        """What: one listing's skill gap — the asked skills the owner has,
        the missing ones, the coverage ratio.
        When: judging fit, or planning how to close a gap.
        Returns: {skills_have, skills_missing, coverage}, or null for an
        unknown role_id.
        Next: generate_cv(role_id) to tailor toward what matched."""
        gap = _read(lambda cur: fetch_job_gap(cur, _owner(cur), role_id))
        if gap is None:
            return with_next(None, state="unknown role_id",
                             call="get_apply_queue",
                             why="pick a listing that exists")
        return with_next(gap, state=f"coverage {gap.get('coverage')}",
                         call="generate_cv",
                         why="tailor the CV toward what matched")

    @mcp.tool(annotations=READ, output_schema=envelope_schema(_QUEUE_RESULT))
    def get_apply_queue(limit: int = 20) -> dict:
        """What: the ranked apply queue — open, local, in-scope roles ordered
        by fit, sponsor confidence, then recency, each with its ranking
        receipts and salary-wall verdict.
        When: every morning; this is what the owner applies from.
        Returns: up to `limit` queue rows.
        Next: get_job(role_id) to read one before applying."""
        rows = _read(lambda cur: fetch_queue(cur, _owner(cur), limit))
        if rows:
            return with_next(rows, state=f"{len(rows)} in the queue",
                             call="get_job",
                             why="read one listing before applying")
        return with_next(rows, state="queue empty", call="start_pipeline",
                         why="refresh discovery/fetch to fill the queue")

    @mcp.tool(annotations=READ)
    def get_job(role_id: int) -> dict:
        """What: one listing's full record, any status — description,
        sponsorship and salary included.
        When: before applying, or when a queue row needs its detail.
        Returns: the listing, or null for an unknown role_id.
        Next: get_job_gap(role_id) to see fit and what is missing."""
        job = _read(lambda cur: fetch_job(cur, _owner(cur), role_id))
        if job is None:
            return with_next(None, state="unknown role_id",
                             call="get_apply_queue",
                             why="pick a listing that exists")
        return with_next(job, state=f"{job.get('role_status')} listing",
                         call="get_job_gap",
                         why="see fit and what would close the gap")

    @mcp.tool(annotations=READ)
    def get_job_history(role_id: int, limit: int = 50) -> dict:
        """What: a listing's life story — appeared / changed (field diffs) /
        closed / reopened, newest first.
        When: judging how fresh or volatile a listing is.
        Returns: up to `limit` events.
        Next: get_job(role_id) for the current record."""
        rows = _read(lambda cur: history_for_role(cur, _owner(cur), role_id, limit))
        return with_next(rows, state=f"{len(rows)} events", call="get_job",
                         why="read the current record")

    @mcp.tool(annotations=READ)
    def get_skill_gaps(limit: int = 20, role_words: str | None = None) -> dict:
        """What: skills roles ask for that the owner lacks, ranked by demand.
        Covers the fit queue by default; role_words ("care assistant") ranks
        over every stored listing matching those words, any industry.
        When: planning learning, or explaining low coverage.
        Returns: up to `limit` gap rows (skill, type, demand; the role_words
        path adds i_have_it).
        Next: get_apply_queue to see the roles behind the demand."""
        if role_words and role_words.strip():
            rows = _read(lambda cur: _gaps_for_words(
                cur, _owner(cur), role_words, limit=limit))
        else:
            rows = _read(lambda cur: fetch_skill_gaps(cur, _owner(cur), limit))
        return with_next(rows, state=f"{len(rows)} gaps", call="get_apply_queue",
                         why="see the roles asking for these skills")

    @mcp.tool(annotations=READ)
    def skills_closest_to_closing(limit: int = 10) -> dict:
        """What: the owner's open skills ranked by how LITTLE it takes to
        close each — cheapest first, not most-demanded first. Tiers: "prove
        it" (held and asked for, but no confirmed fact evidences it, so a CV
        cannot claim it — one sentence closes it), "finish it" (in progress),
        "learn it" (not held). Every row carries the demand it was ranked on.
        When: the owner asks what to do next, or why a CV looks thin.
        Returns: {ranking, basis} — basis says how many were not shown, so a
        capped list never reads as the whole list.
        Next: record_experience to close a "prove it" row."""
        result = _read(lambda cur: _closest(cur, _owner(cur), limit=limit))
        basis = result["basis"]
        cheap = sum(1 for r in result["ranking"] if r["tier"] == "prove it")
        return with_next(
            result,
            state=f"{basis['ranked']} ranked, {basis['not_shown']} not shown",
            call="record_experience" if cheap else "get_skill_gaps",
            why=f"{cheap} skill(s) need only a fact to become CV-usable"
                if cheap else "nothing is one sentence away — see what to learn")

    @mcp.tool(annotations=READ)
    def get_run_report(run_id: int | None = None) -> dict:
        """What: a pipeline run's report card — per-stage status, summaries,
        durations. Latest run by default, or a given run_id.
        When: checking the machine ran, or diagnosing a failed stage.
        Returns: the run report, or null if none match.
        Next: start_pipeline to run again, or daily_brief for the agenda."""
        report = _read(latest_run) if run_id is None else _read(run_report, run_id)
        if report is None:
            return with_next(None, state="no runs recorded",
                             call="start_pipeline", why="run the pipeline once")
        failed = [s.get("name") for s in report.get("stages", [])
                  if not s.get("ok", True)]
        if failed:
            return with_next(report, state=f"failed stages: {failed}",
                             call="start_pipeline", why="retry after the failure")
        return with_next(report, state=f"run {report.get('run_id')} ok",
                         call="daily_brief", why="back to the agenda")

    @mcp.tool(annotations=READ)
    def get_criteria() -> dict:
        """What: the owner's active search criteria — target roles, salary
        floor, wall thresholds, kill-words. Never includes secrets.
        When: checking what the sieves filter on.
        Returns: the criteria record.
        Next: set_criteria to adjust the numeric bounds."""
        criteria = _read(lambda cur: asdict(load_criteria(cur)))
        return with_next(
            criteria,
            state=f"{len(criteria.get('role_patterns', []))} target roles",
            call="set_criteria", why="adjust if these bounds look wrong")
