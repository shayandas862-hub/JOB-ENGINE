"""Action tools — the wrappers a client AI uses to change engine state.

Each is a thin skin over ONE tested engine write (or the pipeline trigger),
wrapped in the contract-v2 envelope. The server holds no business logic: the
SQL and the whitelists live in src/. Nothing here returns a secret.
Provisional-until-confirmed still holds — these record what *you* decided
(the engine never applies for you), and every action writes an mcp_audit row
(arg/result summary only, never a secret) in its own transaction.
"""
from __future__ import annotations

from fastmcp import FastMCP

from applyqueue import mark_applied as _mark_applied
from applyqueue import snooze_listing as _snooze
from audit import record as _audit
from criteria.writer import add_target_company as _add_company
from criteria.writer import set_numeric_criterion as _set_criterion
from cv.filing import regenerate_cv_card as _regen_cv
from discover.company import classify_from_url as _classify_from_url
from discover.company import discover_company as _discover_company
from discover.promote import promote_from_census as _promote
from mcp_server.annotations import writes
from mcp_server.contract import with_next
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn
from notify.push import send_test as _send_test
from pipeline.trigger import preview_pipeline as _preview
from pipeline.trigger import start_pipeline as _start

# Friendly tool argument -> the constraint kind stored in my_constraints.
_CRITERION_KINDS = {
    "salary_floor": "salary_floor",
    "threshold_standard": "salary_threshold_standard",
    "threshold_new_entrant": "salary_threshold_new_entrant",
}


def _run_action(tool_name: str, args_summary: dict, action) -> dict:
    """Run a DB action and audit it in the same transaction, so the audit trail
    exactly reflects what committed."""
    with get_conn() as conn, conn.cursor() as cur:
        result = action(cur)
        _audit(cur, tool_name, args_summary, result)
    return result


def register(mcp: FastMCP) -> None:
    """Hang the action tools on the server."""

    @mcp.tool(annotations=writes(idempotent=True))
    def mark_applied(role_id: int) -> dict:
        """What: record that you applied to a listing (stamps today's date).
        The engine never applies — this only logs that a human did.
        When: immediately after the human submits a real application.
        Returns: {role_id, applied, role_title}; applied false = unknown id.
        Next: daily_brief for the next item."""
        def act(cur):
            title = _mark_applied(cur, _owner(cur), role_id)
            return {"role_id": role_id, "applied": title is not None, "role_title": title}
        result = _run_action("mark_applied", {"role_id": role_id}, act)
        return with_next(
            result,
            state="applied recorded" if result["applied"] else "unknown role_id",
            call="daily_brief", why="next item on the agenda")

    @mcp.tool(annotations=writes(idempotent=True))
    def snooze_listing(role_id: int) -> dict:
        """What: snooze a listing so it stops appearing in nudge digests.
        When: the owner has seen it and decided not now.
        Returns: {role_id, snoozed, role_title}.
        Next: daily_brief to carry on."""
        def act(cur):
            title = _snooze(cur, _owner(cur), role_id)
            return {"role_id": role_id, "snoozed": title is not None, "role_title": title}
        result = _run_action("snooze_listing", {"role_id": role_id}, act)
        return with_next(
            result,
            state="snoozed" if result["snoozed"] else "unknown role_id",
            call="daily_brief", why="back to the agenda")

    @mcp.tool(annotations=writes(idempotent=True))
    def set_criteria(salary_floor: float | None = None,
                     threshold_standard: float | None = None,
                     threshold_new_entrant: float | None = None) -> dict:
        """What: adjust the owner's numeric criteria — salary floor and the
        two salary-wall thresholds. Only the values you pass change.
        When: the queue's salary cut looks wrong for the owner.
        Returns: {updated: {...}} — exactly what changed.
        Next: get_apply_queue for the re-ranked queue."""
        updates = {name: val for name, val in (
            ("salary_floor", salary_floor),
            ("threshold_standard", threshold_standard),
            ("threshold_new_entrant", threshold_new_entrant),
        ) if val is not None}
        if not updates:
            return with_next({"updated": {}}, state="nothing to change",
                             call="get_criteria", why="see the current values")

        def act(cur):
            owner = _owner(cur)
            for name, val in updates.items():
                _set_criterion(cur, owner, _CRITERION_KINDS[name], val)
            return {"updated": updates}
        result = _run_action("set_criteria", updates, act)
        return with_next(result, state=f"{len(updates)} value(s) updated",
                         call="get_apply_queue",
                         why="the queue re-ranks under the new bounds")

    @mcp.tool(annotations=writes())
    def add_target_company(company_name: str, careers_url: str | None = None) -> dict:
        """What: add a company to track by name, optionally with its careers
        URL.
        When: the owner names a company the machine is not watching yet.
        Returns: {company_id, company_name}.
        Next: discover_company(company_name) to probe its board."""
        def act(cur):
            company_id = _add_company(cur, _owner(cur), company_name, careers_url)
            return {"company_id": company_id, "company_name": company_name}
        result = _run_action(
            "add_target_company",
            {"company_name": company_name, "careers_url": careers_url}, act)
        return with_next(result, state="company added", call="discover_company",
                         why="probe its board so jobs start flowing")

    @mcp.tool(annotations=writes(idempotent=True))
    def promote_company(org_name_norm: str) -> dict:
        """What: manually promote a census company onto the fetch list — the
        human override for what the nightly rule does automatically on clear
        passes. Copies the board straight from the census card, no re-probe.
        When: a census company the rule did not promote should be watched.
        Returns: outcome promoted / already_tracked / no_board (with probe
        evidence) / not_found. Use org_name_norm from
        list_software_companies.
        Next: start_pipeline to fetch its jobs now, or wait for tonight."""
        def act(cur):
            return _promote(cur, _owner(cur), org_name_norm)
        result = _run_action("promote_company", {"org_name_norm": org_name_norm}, act)
        outcome = result.get("outcome")
        if outcome == "promoted":
            return with_next(result, state="promoted", call="start_pipeline",
                             why="fetch its jobs now instead of waiting for tonight")
        if outcome == "no_board":
            return with_next(result, state="no board on the census card",
                             call="classify_from_url",
                             why="find the careers URL and onboard it directly")
        return with_next(result, state=outcome or "unknown",
                         call="list_software_companies",
                         why="pick a promotable card")

    @mcp.tool(annotations=writes(open_world=True))
    def discover_company(company_name: str) -> dict:
        """What: discover a company by name — if its public job board is found
        it joins the fetch list with a sponsor-register verdict.
        When: onboarding a company by name, no URL known yet.
        Returns: the probe outcome; on failure, the evidence gathered.
        Next: classify_from_url with the careers URL if no board was found;
        start_pipeline if it onboarded."""
        def act(cur):
            return _discover_company(cur, _owner(cur), company_name)
        result = _run_action("discover_company", {"company_name": company_name}, act)
        onboarded = bool(result.get("company_id"))
        if onboarded:
            return with_next(result, state="onboarded", call="start_pipeline",
                             why="fetch its jobs now")
        return with_next(result, state="no board found", call="classify_from_url",
                         why="hunt the careers URL and onboard it directly")

    @mcp.tool(annotations=writes(open_world=True))
    def classify_from_url(company_name: str, careers_url: str) -> dict:
        """What: onboard a company from its ATS board URL when
        discover_company could not guess it. Verifies the board lists jobs,
        then adds the company with its sponsor-register verdict.
        When: you found the real careers/board URL yourself.
        Returns: the classification outcome and company record.
        Next: start_pipeline to fetch its jobs now."""
        def act(cur):
            return _classify_from_url(cur, _owner(cur), company_name, careers_url)
        result = _run_action(
            "classify_from_url",
            {"company_name": company_name, "careers_url": careers_url}, act)
        return with_next(result, state=str(result.get("outcome", "done")),
                         call="start_pipeline", why="fetch its jobs now")

    @mcp.tool(annotations=writes(open_world=True))
    def generate_cv(role_id: int, emphasis: str | None = None) -> dict:
        """What: re-tailor and re-file a listing's CV, optionally emphasising
        comma-separated skills (e.g. 'RAG, evaluation'). Every line traces to
        a verified fact — the truth gate falls back to the plain fact.
        Updates the listing's Notion card.
        When: before applying to a queue listing.
        Returns: a summary + the card link. The engine never applies.
        Next: mark_applied(role_id) after you actually apply."""
        emphasis_list = [e.strip() for e in (emphasis or "").split(",") if e.strip()]

        def act(cur):
            return _regen_cv(cur, _owner(cur), role_id, emphasis=emphasis_list)
        result = _run_action("generate_cv", {"role_id": role_id, "emphasis": emphasis}, act)
        return with_next(result, state="CV filed", call="mark_applied",
                         why="record it once you actually apply")

    @mcp.tool(annotations=writes(idempotent=True))
    def preview_pipeline() -> dict:
        """What: preview what tonight's run WOULD nudge, without running it —
        a dry run of the same run.py: no fetches, no sends, no stamps, no
        report. Takes seconds, so this waits for the answer.
        When: checking what the queue would deliver before a real run.
        Returns: {dry_run, returncode, output tail}.
        Next: start_pipeline to actually run it."""
        result = _preview()
        with get_conn() as conn, conn.cursor() as cur:
            _audit(cur, "preview_pipeline", {},
                   {"returncode": result["returncode"]})
        return with_next(
            result,
            state=f"dry run, returncode {result['returncode']}",
            call="start_pipeline", why="run it for real")

    @mcp.tool(annotations=writes(open_world=True))
    def start_pipeline() -> dict:
        """What: start a real pipeline run now and return straight away — the
        same run.py the scheduler uses, run lock respected, so a double-start
        exits cleanly. The run continues after this call returns.
        When: something changed (new company, new rule) and tonight is too far
        away. A run takes ~12 minutes.
        Returns: {started, log_path} — no returncode; it is still running.
        Next: get_run_report for the per-stage card once it finishes."""
        with get_conn() as conn, conn.cursor() as cur:
            owner = _owner(cur)
        result = _start(owner=owner)
        with get_conn() as conn, conn.cursor() as cur:
            _audit(cur, "start_pipeline", {}, result)
        return with_next(
            result, state="run started detached",
            call="get_run_report", why="read the per-stage report card when it lands")

    @mcp.tool(annotations=writes(open_world=True))
    def send_test_nudge() -> dict:
        """What: send a one-off test push to the notification channel. Reports
        whether a channel is set and whether it sent — never the channel.
        When: checking nudges are wired before relying on them.
        Returns: {channel_configured, sent}.
        Next: daily_brief to carry on."""
        result = _run_action("send_test_nudge", {},
                             lambda cur: _send_test(cur, _owner(cur)))
        return with_next(result, state="sent" if result.get("sent") else "not sent",
                         call="daily_brief", why="back to the agenda")
